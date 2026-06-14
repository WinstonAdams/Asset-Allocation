"""資產配置佔比、漂移與淨值的純運算服務。

本服務為純運算，不碰 I/O、不依賴 Streamlit。三個資料層方法各對應一類圖表：
snapshot 供圓餅圖（選定月份的資產佔比）、drift_series 供堆疊面積圖（各分類佔比
隨月份變化）、net_worth_series 供淨值折線圖（跨月淨值趨勢，可疊加總資產/總負債線）。

配置口徑只看資產：佔比的分子與分母皆僅由資產組成，負債不出現在任何佔比中；
負債只在淨值口徑以負向參與（淨值＝總資產 − 總負債）。佔比一律以百分比（0–100）
表示，與目標比重同單位。月度序列以「有資料的月份」為節點，缺月直接跳過、不補插。
某月某項目列出但市值留空（仍持有未更新）時不貢獻該月市值。

某月資產市值合計為 0（如當月全數出清）時，佔比分母為 0、無法定義，該月略過不
產生任何佔比節點，使除以零的未定義行為不外漏到圖表。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import HOLDING_KIND, MONTHLY_RECORDS_TABLE
from asset_lab.core.utils import parse_year_month
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import AllocationSnapshot, DriftRow, NetWorthPoint
from asset_lab.models.target import TargetAllocationModel

# 佔比以百分比（0–100）表示，與目標比重同單位。
_PERCENT_BASE = 100.0

# drift_series 輸出長表的欄位：年月 × 分類 × 該月該分類的資產佔比（%）。
_DRIFT_YEAR_MONTH = "year_month"
_DRIFT_DIMENSION_KEY = "dimension_key"
_DRIFT_WEIGHT = "weight"

# 配置佔比的兩種粒度：按單一資產項目、按資產分類彙總。
_BY_HOLDING = "holding"
_BY_CATEGORY = "category"


class AllocationService:
    """配置佔比、漂移與淨值的資料層運算。建構子無依賴（純運算）。"""

    def __init__(self) -> None:
        """初始化配置服務。本服務無外部依賴，僅做加總與佔比運算。"""

    def snapshot(
        self,
        *,
        month_records: list[MonthlyRecordModel],
        holdings: list[HoldingModel],
        by: str,
    ) -> list[AllocationSnapshot]:
        """計算選定月份的資產配置佔比，供圓餅圖（僅資產，不含負債）。

        依粒度彙總資產市值：by='holding' 以項目名為鍵、by='category' 以資產分類為鍵。
        佔比 = 該鍵市值 ÷ 當月資產市值合計 × 100（%）。負債不參與分子與分母；
        市值留空（None）的項目不貢獻市值。當月資產市值合計為 0 時佔比無法定義，
        回傳空清單（見模組說明的零合計決策）。

        Args:
            month_records: 選定月份的月度紀錄清單（同一 year_month）。
            holdings: 項目主檔清單，提供 kind / name / category。
            by: 佔比粒度，'holding'（按項目）或 'category'（按分類）。

        Returns:
            AllocationSnapshot 清單，每筆含年月、維度鍵、市值與佔比（%）；
            無有效資產市值時為空清單。

        Raises:
            ValueError: by 非 'holding' / 'category'。
        """
        holdings_by_id = {h.holding_id: h for h in holdings}
        value_by_key: dict[str, float] = {}
        year_month: str | None = None
        for record in month_records:
            holding = holdings_by_id.get(record.holding_id)
            if holding is None or holding.kind != HOLDING_KIND.ASSET:
                continue
            if record.market_value is None:
                continue
            year_month = record.year_month
            key = self._dimension_key(holding, by)
            value_by_key[key] = value_by_key.get(key, 0.0) + record.market_value

        total = sum(value_by_key.values())
        if year_month is None or total == 0:
            return []

        return [
            AllocationSnapshot(
                year_month=year_month,
                dimension_key=key,
                market_value=value,
                weight=value / total * _PERCENT_BASE,
            )
            for key, value in value_by_key.items()
        ]

    def drift_series(
        self, *, range_df: pd.DataFrame, holdings: list[HoldingModel]
    ) -> pd.DataFrame:
        """計算各資產分類佔比隨月份的變化，供堆疊面積圖（僅資產，不含負債）。

        以有資料月為節點（缺月不補點），每個節點按資產分類彙總當月市值並換算為佔比
        （該分類市值 ÷ 當月資產市值合計 × 100）。負債不形成任何分類列；市值留空的
        項目不貢獻市值；某月資產市值合計為 0 時該月略過、不產生節點。

        Args:
            range_df: 區間月度紀錄 DataFrame，含 holding_id、year_month、market_value、
                net_investment 欄。
            holdings: 項目主檔清單，提供 kind / category。

        Returns:
            長表 DataFrame，欄為 year_month、dimension_key（分類）、weight（%）；
            依年月、分類排序；無有效資產資料時為空 DataFrame。
        """
        columns = [_DRIFT_YEAR_MONTH, _DRIFT_DIMENSION_KEY, _DRIFT_WEIGHT]
        asset_records = self._asset_records(range_df, holdings)
        if asset_records.empty:
            return pd.DataFrame(columns=columns)

        category_by_id = {
            h.holding_id: h.category for h in holdings if h.kind == HOLDING_KIND.ASSET
        }
        rows: list[dict[str, object]] = []
        for year_month in self._sorted_data_months(asset_records):
            month_slice = asset_records[
                asset_records[MONTHLY_RECORDS_TABLE.YEAR_MONTH] == year_month
            ]
            value_by_category = self._sum_by_category(month_slice, category_by_id)
            total = sum(value_by_category.values())
            if total == 0:
                continue
            for category in sorted(value_by_category):
                rows.append(
                    {
                        _DRIFT_YEAR_MONTH: year_month,
                        _DRIFT_DIMENSION_KEY: category,
                        _DRIFT_WEIGHT: value_by_category[category] / total * _PERCENT_BASE,
                    }
                )
        return pd.DataFrame(rows, columns=columns)

    def net_worth_series(
        self, *, range_df: pd.DataFrame, holdings: list[HoldingModel]
    ) -> list[NetWorthPoint]:
        """計算跨月淨值趨勢，供淨值折線圖（可疊加總資產/總負債線）。

        以有資料月為節點（缺月不補點），每個節點彙總當月總資產（資產項目市值合計）
        與總負債（負債項目餘額合計），淨值 = 總資產 − 總負債。淨值不設下限，負債大於
        資產時為負數。市值/餘額留空（None）的項目不貢獻當月金額。

        Args:
            range_df: 區間月度紀錄 DataFrame，含 holding_id、year_month、market_value、
                net_investment 欄。
            holdings: 項目主檔清單，提供 kind 以區分資產與負債。

        Returns:
            NetWorthPoint 清單，依年月排序，每筆含總資產、總負債與淨值；
            無資料時為空清單。
        """
        if range_df.empty:
            return []

        kind_by_id = {h.holding_id: h.kind for h in holdings}
        points: list[NetWorthPoint] = []
        for year_month in self._sorted_data_months(range_df):
            month_slice = range_df[range_df[MONTHLY_RECORDS_TABLE.YEAR_MONTH] == year_month]
            total_assets = 0.0
            total_liabilities = 0.0
            for row in month_slice.itertuples(index=False):
                market_value = getattr(row, MONTHLY_RECORDS_TABLE.MARKET_VALUE)
                if market_value is None or pd.isna(market_value):
                    continue
                kind = kind_by_id.get(getattr(row, MONTHLY_RECORDS_TABLE.HOLDING_ID))
                if kind == HOLDING_KIND.ASSET:
                    total_assets += float(market_value)
                elif kind == HOLDING_KIND.LIABILITY:
                    total_liabilities += float(market_value)
            points.append(
                NetWorthPoint(
                    year_month=year_month,
                    total_assets=total_assets,
                    total_liabilities=total_liabilities,
                    net_worth=total_assets - total_liabilities,
                )
            )
        return points

    def compute_drift(
        self,
        *,
        snapshot: list[AllocationSnapshot],
        targets: list[TargetAllocationModel],
        threshold: float,
    ) -> list[DriftRow]:
        """計算各分類現況佔比相對目標比重的偏離，並判定是否需再平衡。

        以分類粒度的現況佔比（snapshot，by='category'）對齊目標比重，逐分類算
        偏離 = 現況% − 目標%（百分點）。偏離絕對值嚴格超過門檻才標示需再平衡，
        恰好等於門檻不標示。目標比重為選用設定：只判定有設目標的分類，未設目標的
        分類不顯示偏離、不判定再平衡；設了目標但當月無持有的分類現況%視為 0，仍
        計算偏離（偏離 = −目標%）。現況%、目標%、偏離一律以百分比（0–100）表示。

        Args:
            snapshot: 選定月份的分類現況佔比清單（dimension_key 為資產分類，weight 為 %）。
            targets: 各分類目標比重清單（target_weight 為 %，0–100）。
            threshold: 再平衡偏離門檻，以百分點計（如 5.0）。

        Returns:
            DriftRow 清單，每筆含分類、現況%、目標%、偏離百分點與是否需再平衡；
            僅含有設目標的分類，未設目標時為空清單。
        """
        current_by_category = {row.dimension_key: row.weight for row in snapshot}
        rows: list[DriftRow] = []
        for target in targets:
            # 設了目標但當月無該分類持有時現況視為 0%，仍須呈現負向偏離
            current_weight = current_by_category.get(target.category, 0.0)
            drift = current_weight - target.target_weight
            rows.append(
                DriftRow(
                    category=target.category,
                    current_weight=current_weight,
                    target_weight=target.target_weight,
                    drift=drift,
                    needs_rebalance=abs(drift) > threshold,
                )
            )
        return rows

    @staticmethod
    def _dimension_key(holding: HoldingModel, by: str) -> str:
        """取得佔比彙總的維度鍵：按項目用名稱、按分類用資產分類。"""
        if by == _BY_HOLDING:
            return holding.name
        if by == _BY_CATEGORY:
            return holding.category
        raise ValueError(f"未知的佔比粒度：{by!r}")

    @staticmethod
    def _asset_records(range_df: pd.DataFrame, holdings: list[HoldingModel]) -> pd.DataFrame:
        """過濾出資產項目的月度紀錄；負債一律排除。"""
        if range_df.empty:
            return range_df
        asset_ids = {h.holding_id for h in holdings if h.kind == HOLDING_KIND.ASSET}
        return range_df[range_df[MONTHLY_RECORDS_TABLE.HOLDING_ID].isin(asset_ids)]

    @staticmethod
    def _sorted_data_months(records: pd.DataFrame) -> list[str]:
        """抽出有資料月份並依時間排序（缺月自然不出現，不補插）。"""
        return sorted(
            {str(ym) for ym in records[MONTHLY_RECORDS_TABLE.YEAR_MONTH]},
            key=parse_year_month,
        )

    @staticmethod
    def _sum_by_category(
        month_slice: pd.DataFrame, category_by_id: dict[int, str]
    ) -> dict[str, float]:
        """彙總單月各資產分類的市值合計；留空市值不貢獻。"""
        value_by_category: dict[str, float] = {}
        for row in month_slice.itertuples(index=False):
            market_value = getattr(row, MONTHLY_RECORDS_TABLE.MARKET_VALUE)
            if market_value is None or pd.isna(market_value):
                continue
            category = category_by_id.get(getattr(row, MONTHLY_RECORDS_TABLE.HOLDING_ID))
            value_by_category[category] = value_by_category.get(category, 0.0) + float(market_value)
        return value_by_category
