"""城市總覽的資料組裝（純運算）。"""

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import HOLDING_KIND, HOLDING_PURPOSE
from asset_lab.models.holding import HoldingModel
from asset_lab.models.results import CityHolding, CityTimeline
from asset_lab.services.affordability_service import AffordabilityService
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.house_service import HouseService
from asset_lab.services.protocol_service import ProtocolService
from asset_lab.services.return_service import ReturnService


class CityService:
    """城市總覽的資料組裝：依月份切片後重用既有 Service，不新增財務計算。"""

    def __init__(
        self,
        *,
        return_service: ReturnService,
        protocol_service: ProtocolService,
        allocation_service: AllocationService,
        house_service: HouseService,
        affordability_service: AffordabilityService,
        min_data_months: int,
        rebalance_threshold: float,
    ) -> None:
        self._return_service = return_service
        self._protocol_service = protocol_service
        self._allocation_service = allocation_service
        self._house_service = house_service
        self._affordability_service = affordability_service
        self._min_data_months = min_data_months
        self._rebalance_threshold = rebalance_threshold

    def build_timeline(
        self, *, holdings: list[HoldingModel], records_df: pd.DataFrame
    ) -> CityTimeline:
        """產出月份清單、進版位的項目、各月數值與兩個高度分母。

        進版位的項目為非購屋用途且至少有一筆月度紀錄者（只有留空列也算）；月份清單含
        所有項目（負債、購屋項目）出現過的年月。峰值只看非空市值，留空月份不參與。

        Args:
            holdings: 全量持有主檔（含購屋用途項目、負債）。
            records_df: 全量月度紀錄（holding_id、year_month、market_value）。

        Returns:
            城市時間軸；沒有任何月度紀錄時 months 為空清單。
        """
        months = sorted(set(records_df["year_month"]))
        values_by_holding = self._month_values_by_holding(records_df)

        city_holdings = [
            self._to_city_holding(holding, values_by_holding[holding.holding_id])
            for holding in sorted(holdings, key=lambda h: h.holding_id)
            if holding.purpose != HOLDING_PURPOSE.HOUSE
            and holding.holding_id in values_by_holding
        ]
        return CityTimeline(
            months=months,
            latest_month=months[-1] if months else None,
            holdings=city_holdings,
            max_asset_value=self._max_peak(city_holdings, kind=HOLDING_KIND.ASSET),
            max_liability_value=self._max_peak(city_holdings, kind=HOLDING_KIND.LIABILITY),
        )

    @staticmethod
    def _month_values_by_holding(records_df: pd.DataFrame) -> dict[int, dict[str, float | None]]:
        """逐項目整理「月份 -> 市值」；有列但市值留空者值為 None。"""
        result: dict[int, dict[str, float | None]] = {}
        for row in records_df.itertuples(index=False):
            value = None if pd.isna(row.market_value) else float(row.market_value)
            result.setdefault(int(row.holding_id), {})[row.year_month] = value
        return result

    @staticmethod
    def _to_city_holding(
        holding: HoldingModel, month_values: dict[str, float | None]
    ) -> CityHolding:
        """組出單一版位項目；峰值取非空市值最大者，全部留空為 0。"""
        filled = [value for value in month_values.values() if value is not None]
        return CityHolding(
            holding_id=holding.holding_id,
            name=holding.name,
            kind=holding.kind,
            category=holding.category,
            peak_value=max(filled, default=0.0),
            month_values=dict(sorted(month_values.items())),
        )

    @staticmethod
    def _max_peak(city_holdings: list[CityHolding], *, kind: str) -> float:
        """指定性質的版位項目峰值最大者（高度分母）；沒有項目為 0。"""
        return max((h.peak_value for h in city_holdings if h.kind == kind), default=0.0)
