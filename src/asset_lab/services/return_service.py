"""報酬率計算服務。

本服務為純運算，不碰 I/O、不依賴 Streamlit。報酬率分三條互不汙染的口徑：
時間加權報酬率（TWR）與現金流年化報酬率（MWR/XIRR）皆以「初始市值」起算記錄後
績效；賺賠金額與簡單總報酬率以「初始成本」起算、含記錄前歷史。初始市值與初始成本
必須隔離——記錄前的價差只屬於賺賠口徑，不可被算成 TWR/MWR 的第一期報酬，故各管線
的函式簽名只接受自身基準參數，從介面上杜絕混用。

MWR 以 XIRR 數值求解，無正負交替、無解或結果非有限值皆屬可預期的數值邊界，
降級回 (None, 'not_converged') 由上層改以「無法計算」呈現，不拖垮並列的 TWR 與賺賠。

月度序列以「有資料的月份」為節點，相鄰兩個有資料月之間視為一段期間；整月缺漏
直接跳過、不補插值，避免非真實節點稀釋真實期間報酬。
"""

# ==== 原生（標準庫） ====
import math
from datetime import date

# ==== 第三方套件 ====
import pandas as pd
import pyxirr

# ==== 專案內部 ====
from asset_lab.core.constants import HOLDING_KIND, MONTHLY_RECORDS_TABLE
from asset_lab.core.utils import months_between, parse_year_month, year_month_add
from asset_lab.models.holding import HoldingModel
from asset_lab.models.results import CumulativeTwrPoint, ReturnResult

# MWR 不收斂（無正負交替、求解失敗或結果非有限值）時的降級狀態旗標。
_MWR_OK = "ok"
_MWR_NOT_CONVERGED = "not_converged"

# 報酬率三維度。整體不分組（單一結果）、分類依資產分類彙總、單一標的以項目為原子。
_DIMENSION_OVERALL = "overall"
_DIMENSION_CATEGORY = "category"
_DIMENSION_HOLDING = "holding"

# 滿此月跨度才年化；未滿只顯示期間累積報酬（涵蓋月數 = 起訖月相差 + 1）。
_ANNUALIZE_MIN_MONTHS = 12


class ReturnService:
    """報酬率三口徑計算。建構子無依賴（純運算）。"""

    def __init__(self) -> None:
        """初始化報酬率服務。本服務無外部依賴，僅做數值運算。"""

    def compute_twr(self, *, monthly: pd.DataFrame, initial_market_value: float) -> float | None:
        """計算區間時間加權報酬率（TWR），逐段連乘且排除當月淨投入。

        以「初始市值」為首段期初，依時間排序後相鄰兩個有資料月為一段期間，
        每段報酬 =（期末市值 − 當月淨投入 − 期初市值）÷ 期初市值，逐段連乘後減一。
        當月淨投入視為月底發生，不賺取當月報酬，故須自期末市值扣除。
        期初市值為 0 的建倉月會造成除以 0，該段不納入連乘，自下一個期初大於 0 的
        期間起算。留空（None）的市值沿用上一個有值月份（見 _value_series）。
        若無任何有效連乘段（序列為空、僅建倉月、所有期初皆為 0），回傳 None。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄；
                僅含有資料月，market_value 可為 None 表當月留空。
            initial_market_value: 首段期初市值，即記錄起點的市值基準。

        Returns:
            區間 TWR（百分比小數，如 0.331 表 33.1%）；無有效連乘段時為 None。
        """
        values, net_investments = self._value_series(monthly)

        opening = initial_market_value
        cumulative = 1.0
        has_segment = False
        for end_value, net_investment in zip(values, net_investments, strict=True):
            if end_value is None:
                # 留空且無前值可沿用：無法形成有效期末，跳過此段並維持期初基準
                continue
            if opening != 0:
                cumulative *= (end_value - net_investment) / opening
                has_segment = True
            # 期初為 0 的建倉段不納入連乘，但其期末市值成為下一段的期初
            opening = end_value

        if not has_segment:
            return None
        return cumulative - 1.0

    def compute_mwr(
        self, *, monthly: pd.DataFrame, initial_market_value: float
    ) -> tuple[float | None, str]:
        """計算現金流年化內部報酬率（MWR/XIRR），不收斂時降級。

        以「初始市值」為記錄起點的現金流基準（與賺賠口徑的初始成本刻意分離）。
        現金流序列組成：初始市值記為期初流出（負）、各有資料月的淨投入依正負號轉
        現金流（投入為流出計負、提領為流入計正）、最後一個有值月份的市值記為終值
        流入（正）。各現金流以對應月份的月初為日期；初始流出落在首個有資料月的前
        一個月（首段期初），使滿一年的純成長正好年化為該年報酬。

        XIRR 屬數值求解：當現金流無正負交替、求解失敗或結果為非有限值（如 inf/nan）
        皆屬可預期的數值邊界而非系統錯誤，一律降級回 (None, 'not_converged')，
        讓上層改以「無法計算」呈現而不中斷其他並列指標（TWR、賺賠）。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄；
                僅含有資料月，market_value 可為 None 表當月留空（沿用前值）。
            initial_market_value: 記錄起點的市值基準，作為期初流出現金流。

        Returns:
            (年化內部報酬率, 狀態旗標)；可收斂時為 (mwr, 'ok')，
            不收斂時為 (None, 'not_converged')。
        """
        dates, amounts = self._cash_flows(monthly, initial_market_value)
        if dates is None:
            return None, _MWR_NOT_CONVERGED

        # silent=True 讓無正負交替等無解情形回 None 而非拋例外；
        # 結果非有限值（如現金流發散出的 inf/nan）同屬不收斂，皆降級不外漏。
        result = pyxirr.xirr(dates, amounts, silent=True)
        if result is None or not math.isfinite(result):
            return None, _MWR_NOT_CONVERGED
        return result, _MWR_OK

    def compute_pnl(
        self, *, monthly: pd.DataFrame, initial_cost: float
    ) -> tuple[float | None, float | None]:
        """計算賺賠金額與簡單總報酬率，以累積成本起算。

        累積成本 = 初始成本 + 後續各月淨投入合計；賺賠金額 = 當前市值 − 累積成本；
        簡單總報酬率 = 賺賠 ÷ 累積成本。初始成本含記錄前的歷史價差，與 TWR 起算的
        初始市值刻意分離。當前市值取最後一個有值月份（留空月沿用前值）。
        累積成本為 0 時簡單總報酬率無意義，回傳 None（賺賠金額仍可呈現）。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄；
                僅含有資料月，market_value 可為 None 表當月留空。
            initial_cost: 累積成本的起算基準，含記錄前已投入的歷史成本。

        Returns:
            (賺賠金額, 簡單總報酬率) 二元組；無有值月份時賺賠為 None，
            累積成本為 0 時簡單總報酬率為 None。
        """
        values, net_investments = self._value_series(monthly)

        cumulative_cost = initial_cost + sum(net_investments)
        current_value = next((value for value in reversed(values) if value is not None), None)
        if current_value is None:
            return None, None

        pnl = current_value - cumulative_cost
        simple_return = None if cumulative_cost == 0 else pnl / cumulative_cost
        return pnl, simple_return

    def compute_returns(
        self,
        *,
        range_df: pd.DataFrame,
        holdings: list[HoldingModel],
        dimension: str,
        start_ym: str,
        end_ym: str,
    ) -> list[ReturnResult]:
        """彙總指定維度的報酬率結果（整體 / 各分類 / 各單一標的，僅資產）。

        以單一標的為計算原子，分類與整體由其成員標的彙總。每個維度以「該維度自身的
        淨投入序列 ＋ 該維度自身期末市值為終值」獨立計算 TWR/MWR/賺賠：標的層用自身
        序列；分類/整體層為其成員標的同月市值（各自沿用留空前值後）相加、同月淨投入
        相加組成的彙總序列。各維度的初始市值與初始成本為其成員的對應加總。負債一律
        不納入。年化僅在區間涵蓋滿 12 個月時開啟，否則只顯示期間累積報酬。

        Args:
            range_df: 區間月度紀錄 DataFrame，含 holding_id、year_month、market_value、
                net_investment 欄；涵蓋 [start_ym, end_ym]。
            holdings: 項目主檔清單，提供 kind / category / 初始市值 / 初始成本。
            dimension: 維度，須為 'overall' / 'category' / 'holding' 之一。
            start_ym: 區間起月（'YYYY-MM'），用於年化月跨度判定。
            end_ym: 區間訖月（'YYYY-MM'），用於年化月跨度判定。

        Returns:
            該維度的 ReturnResult 清單；overall 為單一結果，category/holding 各組一筆。
        """
        annualized = months_between(start_ym, end_ym) + 1 >= _ANNUALIZE_MIN_MONTHS
        asset_records = self._asset_records(range_df, holdings)

        results: list[ReturnResult] = []
        for dimension_key, member_ids in self._dimension_groups(dimension, holdings):
            monthly = self._aggregate_monthly(asset_records, member_ids)
            initial_market_value, initial_cost = self._dimension_bases(holdings, member_ids)
            results.append(
                self._build_result(
                    dimension=dimension,
                    dimension_key=dimension_key,
                    monthly=monthly,
                    initial_market_value=initial_market_value,
                    initial_cost=initial_cost,
                    annualized=annualized,
                )
            )
        return results

    def cumulative_twr_series(
        self, *, range_df: pd.DataFrame, holdings: list[HoldingModel]
    ) -> list[CumulativeTwrPoint]:
        """產出整體（全體資產彙總）逐有資料月的累積 TWR 序列，供報酬率走勢圖。

        以有資料月為節點（缺月不補點），每個節點的值為自區間起點累積至該月的整體
        TWR。僅含資產；負債不納入。某月某標的市值留空時沿用其上一有值月份（與 TWR
        連乘一致）。無任何有資料月時回空序列。

        Args:
            range_df: 區間月度紀錄 DataFrame，含 holding_id、year_month、market_value、
                net_investment 欄。
            holdings: 項目主檔清單，用於篩出資產與取得整體初始市值。

        Returns:
            逐有資料月的 CumulativeTwrPoint 清單，依月份排序。
        """
        asset_records = self._asset_records(range_df, holdings)
        all_asset_ids = [h.holding_id for h in holdings if h.kind == HOLDING_KIND.ASSET]
        monthly = self._aggregate_monthly(asset_records, all_asset_ids)
        if monthly.empty:
            return []

        initial_market_value, _ = self._dimension_bases(holdings, all_asset_ids)
        ordered = monthly.sort_values(MONTHLY_RECORDS_TABLE.YEAR_MONTH)
        year_months = [str(ym) for ym in ordered[MONTHLY_RECORDS_TABLE.YEAR_MONTH]]

        series: list[CumulativeTwrPoint] = []
        for index in range(len(year_months)):
            # 累積至第 index 個有資料月：取前綴序列計 TWR，得該月的累積報酬節點
            prefix = ordered.iloc[: index + 1]
            cumulative = self.compute_twr(monthly=prefix, initial_market_value=initial_market_value)
            if cumulative is None:
                # 前綴僅含建倉月（期初皆 0）尚無有效連乘段，跳過該節點
                continue
            series.append(
                CumulativeTwrPoint(year_month=year_months[index], cumulative_twr=cumulative)
            )
        return series

    @staticmethod
    def _asset_records(range_df: pd.DataFrame, holdings: list[HoldingModel]) -> pd.DataFrame:
        """過濾出資產項目的月度紀錄；負債一律排除。"""
        asset_ids = {h.holding_id for h in holdings if h.kind == HOLDING_KIND.ASSET}
        if range_df.empty:
            return range_df
        return range_df[range_df[MONTHLY_RECORDS_TABLE.HOLDING_ID].isin(asset_ids)]

    @staticmethod
    def _dimension_groups(
        dimension: str, holdings: list[HoldingModel]
    ) -> list[tuple[str | None, list[int]]]:
        """依維度組出 (維度鍵, 成員 holding_id 清單)；僅含資產。

        overall 為單一組（鍵為 None、成員為全體資產）；category 依資產分類分組
        （鍵為分類名）；holding 每個資產一組（鍵為 holding_id 字串）。
        """
        assets = [h for h in holdings if h.kind == HOLDING_KIND.ASSET]
        if dimension == _DIMENSION_OVERALL:
            return [(None, [h.holding_id for h in assets])]
        if dimension == _DIMENSION_HOLDING:
            return [(str(h.holding_id), [h.holding_id]) for h in assets]
        if dimension == _DIMENSION_CATEGORY:
            grouped: dict[str, list[int]] = {}
            for holding in assets:
                grouped.setdefault(holding.category, []).append(holding.holding_id)
            return [(category, ids) for category, ids in grouped.items()]
        raise ValueError(f"未知的報酬率維度：{dimension!r}")

    @staticmethod
    def _dimension_bases(
        holdings: list[HoldingModel], member_ids: list[int]
    ) -> tuple[float, float]:
        """彙總維度成員的初始市值與初始成本（缺值以 0 計）。"""
        initial_market_value = 0.0
        initial_cost = 0.0
        member_set = set(member_ids)
        for holding in holdings:
            if holding.holding_id not in member_set:
                continue
            initial_market_value += holding.initial_market_value or 0.0
            initial_cost += holding.initial_cost or 0.0
        return initial_market_value, initial_cost

    @staticmethod
    def _aggregate_monthly(asset_records: pd.DataFrame, member_ids: list[int]) -> pd.DataFrame:
        """把維度成員標的彙總成單一月度序列（市值同月相加、淨投入同月相加）。

        以成員各自的有資料月為節點，聯集成該維度的有資料月；某成員某月留空市值時，
        沿用該成員上一有值月份的市值（與單標的 TWR 連乘的沿用語意一致）後才相加，
        未持有（無該月節點）的成員該月不貢獻市值。淨投入同月直接相加（缺月計 0）。

        Args:
            asset_records: 已過濾為資產的月度紀錄 DataFrame。
            member_ids: 該維度的成員 holding_id 清單。

        Returns:
            彙總後的月度序列 DataFrame，含 year_month、market_value、net_investment 欄；
            無任何成員資料時為空 DataFrame。
        """
        columns = [
            MONTHLY_RECORDS_TABLE.YEAR_MONTH,
            MONTHLY_RECORDS_TABLE.MARKET_VALUE,
            MONTHLY_RECORDS_TABLE.NET_INVESTMENT,
        ]
        if asset_records.empty or not member_ids:
            return pd.DataFrame(columns=columns)

        member_set = set(member_ids)
        members = asset_records[asset_records[MONTHLY_RECORDS_TABLE.HOLDING_ID].isin(member_set)]
        if members.empty:
            return pd.DataFrame(columns=columns)

        year_months = sorted(
            {str(ym) for ym in members[MONTHLY_RECORDS_TABLE.YEAR_MONTH]},
            key=parse_year_month,
        )

        market_by_month: dict[str, float] = dict.fromkeys(year_months, 0.0)
        net_by_month: dict[str, float] = dict.fromkeys(year_months, 0.0)
        for holding_id in member_set:
            single = members[members[MONTHLY_RECORDS_TABLE.HOLDING_ID] == holding_id]
            if single.empty:
                continue
            values, nets = ReturnService._value_series(single)
            ordered = single.sort_values(MONTHLY_RECORDS_TABLE.YEAR_MONTH)
            member_months = [str(ym) for ym in ordered[MONTHLY_RECORDS_TABLE.YEAR_MONTH]]
            for month, value, net in zip(member_months, values, nets, strict=True):
                if value is not None:
                    market_by_month[month] += value
                net_by_month[month] += net

        return pd.DataFrame(
            {
                MONTHLY_RECORDS_TABLE.YEAR_MONTH: year_months,
                MONTHLY_RECORDS_TABLE.MARKET_VALUE: [market_by_month[m] for m in year_months],
                MONTHLY_RECORDS_TABLE.NET_INVESTMENT: [net_by_month[m] for m in year_months],
            }
        )

    def _build_result(
        self,
        *,
        dimension: str,
        dimension_key: str | None,
        monthly: pd.DataFrame,
        initial_market_value: float,
        initial_cost: float,
        annualized: bool,
    ) -> ReturnResult:
        """組合三條管線輸出為單一維度的 ReturnResult。"""
        twr = self.compute_twr(monthly=monthly, initial_market_value=initial_market_value)
        mwr, mwr_status = self.compute_mwr(
            monthly=monthly, initial_market_value=initial_market_value
        )
        pnl, simple_return = self.compute_pnl(monthly=monthly, initial_cost=initial_cost)
        return ReturnResult(
            dimension=dimension,
            dimension_key=dimension_key,
            twr=twr,
            mwr=mwr,
            mwr_status=mwr_status,
            simple_return=simple_return,
            pnl_amount=pnl,
            annualized=annualized,
        )

    @staticmethod
    def _cash_flows(
        monthly: pd.DataFrame, initial_market_value: float
    ) -> tuple[list[date] | None, list[float] | None]:
        """組裝供 XIRR 求解的現金流（日期, 金額）序列。

        以有資料月為節點依時間排序：初始市值為期初流出（負），落在首個有資料月的
        前一個月月初；各有資料月的淨投入轉現金流（投入計負、提領計正），落在該月
        月初；最後一個有值月份的市值為終值流入（正）。留空（None）市值沿用前值處理，
        終值取最後一個有值月份。

        無任何有資料月、或無可取得的終值市值（全程留空且無前值）時，無從構成可求解
        的現金流，回 (None, None) 交由呼叫端降級。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄。
            initial_market_value: 期初流出的市值基準。

        Returns:
            (日期清單, 金額清單)；無法構成現金流時為 (None, None)。
        """
        if monthly.empty:
            return None, None

        ordered = monthly.sort_values(MONTHLY_RECORDS_TABLE.YEAR_MONTH)
        year_months = [str(ym) for ym in ordered[MONTHLY_RECORDS_TABLE.YEAR_MONTH]]
        values, net_investments = ReturnService._value_series(ordered)

        terminal_value = next((value for value in reversed(values) if value is not None), None)
        if terminal_value is None:
            return None, None

        # 初始市值流出落在首個有資料月的前一個月月初（首段期初）
        opening_ym = year_month_add(year_months[0], -1)
        dates: list[date] = [ReturnService._month_start(opening_ym)]
        amounts: list[float] = [-initial_market_value]

        last_index = len(year_months) - 1
        for index, year_month in enumerate(year_months):
            # 投入（淨投入為正）為流出計負；提領（淨投入為負）為流入計正
            amount = -net_investments[index]
            if index == last_index:
                # 末月併計終值流入（市值流回）
                amount += terminal_value
            dates.append(ReturnService._month_start(year_month))
            amounts.append(amount)

        return dates, amounts

    @staticmethod
    def _month_start(year_month: str) -> date:
        """將 'YYYY-MM' 轉為該月月初日期，作為現金流發生日。"""
        year, month = parse_year_month(year_month)
        return date(year, month, 1)

    @staticmethod
    def _value_series(monthly: pd.DataFrame) -> tuple[list[float | None], list[float]]:
        """將月度序列依時間排序，並對留空市值沿用上一個有值月份。

        以有資料的月份為節點依 year_month 排序；某月仍在清單但市值留空（None）
        代表仍持有、當月未更新，沿用上一個有值月份的市值，且不視為當月有變動。
        首個有值月份之前若有留空（無前值可沿用）則維持 None。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄。

        Returns:
            (沿用後的市值清單, 淨投入清單)，兩者皆依時間排序、長度一致。
        """
        if monthly.empty:
            return [], []

        ordered = monthly.sort_values(MONTHLY_RECORDS_TABLE.YEAR_MONTH)
        values: list[float | None] = []
        net_investments: list[float] = []
        last_valued: float | None = None
        for _, row in ordered.iterrows():
            raw_value = row[MONTHLY_RECORDS_TABLE.MARKET_VALUE]
            if raw_value is None or pd.isna(raw_value):
                values.append(last_valued)
            else:
                last_valued = float(raw_value)
                values.append(last_valued)
            net_investments.append(float(row[MONTHLY_RECORDS_TABLE.NET_INVESTMENT]))
        return values, net_investments
