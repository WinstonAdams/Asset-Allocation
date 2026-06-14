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
from asset_lab.core.constants import MONTHLY_RECORDS_TABLE
from asset_lab.core.utils import parse_year_month, year_month_add

# MWR 不收斂（無正負交替、求解失敗或結果非有限值）時的降級狀態旗標。
_MWR_OK = "ok"
_MWR_NOT_CONVERGED = "not_converged"


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
