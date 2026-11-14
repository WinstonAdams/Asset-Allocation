"""城市總覽的資料組裝（純運算）。"""

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import CITY_BUILDING_STATUS, HOLDING_KIND, HOLDING_PURPOSE
from asset_lab.core.utils import records_frame_to_models
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParams, SubjectiveTriggerModel
from asset_lab.models.protocol import ProtocolThresholds
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import (
    CityBuildingState,
    CityFrame,
    CityHolding,
    CitySite,
    CityTimeline,
    DriftRow,
    ProtocolStatus,
)
from asset_lab.models.target import TargetAllocationModel
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

    def frame_at(
        self,
        *,
        year_month: str,
        timeline: CityTimeline,
        holdings: list[HoldingModel],
        records_df: pd.DataFrame,
        thresholds: ProtocolThresholds,
        house_params: HouseParams,
        subjective: list[SubjectiveTriggerModel],
        targets: list[TargetAllocationModel],
        current_year: int,
    ) -> CityFrame:
        """算選定月份的天氣、工地、建築狀態與偏離。

        歷史月份以「紀錄截斷到該月」加「排除該月尚未出現的項目」重用既有 Service；
        最新月時兩者都等於沒做，結果與現行頁面一致。

        Args:
            year_month: 選定月份，必須在 timeline.months 內。
            timeline: build_timeline 的結果。
            holdings: 全量持有主檔（含購屋用途項目、負債）。
            records_df: 全量月度紀錄。
            thresholds: 已合併預設的三級回撤門檻。
            house_params: 已合併預設的買房參數。
            subjective: 主觀觸發條件勾選狀態。
            targets: 各分類目標比重。
            current_year: 當前西元年（不從系統時鐘取，由呼叫端傳入）。

        Returns:
            選定月份的城市畫面資料。

        Raises:
            ValueError: year_month 不在 timeline.months。
        """
        if year_month not in timeline.months:
            raise ValueError(f"year_month {year_month} 不在城市月份清單內")

        truncated_df = records_df[records_df["year_month"] <= year_month]
        weather = self._weather_at(
            truncated_df=truncated_df, holdings=holdings, thresholds=thresholds
        )
        site = self._site_at(
            records_df=records_df,
            holdings=holdings,
            year_month=year_month,
            house_params=house_params,
            subjective=subjective,
            current_year=current_year,
        )
        month_models = records_frame_to_models(
            records_df[records_df["year_month"] == year_month]
        )
        snapshot = self._allocation_service.snapshot(
            month_records=month_models, holdings=holdings, by="category"
        )
        drift_rows = self._allocation_service.compute_drift(
            snapshot=snapshot, targets=targets, threshold=self._rebalance_threshold
        )
        return CityFrame(
            year_month=year_month,
            is_latest=year_month == timeline.latest_month,
            weather=weather,
            site=site,
            buildings=self._buildings_at(
                year_month=year_month, timeline=timeline, drift_rows=drift_rows
            ),
            drift_rows=drift_rows,
            house_purpose_categories=self._house_purpose_categories(
                month_models=month_models, holdings=holdings
            ),
        )

    def _weather_at(
        self,
        *,
        truncated_df: pd.DataFrame,
        holdings: list[HoldingModel],
        thresholds: ProtocolThresholds,
    ) -> ProtocolStatus:
        """天氣：截斷紀錄配全量主檔（整體初始市值與總覽頁同口徑）。"""
        series = self._return_service.cumulative_twr_series(
            range_df=truncated_df, holdings=holdings
        )
        return self._protocol_service.assess(
            series=series, thresholds=thresholds, min_data_months=self._min_data_months
        )

    def _site_at(
        self,
        *,
        records_df: pd.DataFrame,
        holdings: list[HoldingModel],
        year_month: str,
        house_params: HouseParams,
        subjective: list[SubjectiveTriggerModel],
        current_year: int,
    ) -> CitySite:
        """工地：bucket 用截斷紀錄與該月已出現的項目，其餘參數用目前設定。"""
        month_records = records_frame_to_models(records_df[records_df["year_month"] <= year_month])
        month_holdings = self._holdings_existing_at(
            holdings=holdings, records_df=records_df, year_month=year_month
        )
        bucket_value = self._house_service.bucket_value(
            month_records=month_records, holdings=month_holdings
        )
        cash_reserve_value = self._house_service.cash_reserve_value(
            month_records=month_records, holdings=month_holdings
        )
        forward_result = self._affordability_service.payment_for_price(
            total_price=house_params.target_total_price,
            down_payment_ratio_pct=house_params.down_payment_ratio,
            test_annual_rate_pct=house_params.test_annual_rate,
            loan_years=house_params.loan_years,
            monthly_income=house_params.monthly_after_tax_income,
        )
        progress = self._house_service.bucket_progress(
            bucket_value=bucket_value, params=house_params, current_year=current_year
        )
        checklist = self._house_service.assess_triggers(
            params=house_params,
            bucket_value=bucket_value,
            cash_reserve_value=cash_reserve_value,
            forward_result=forward_result,
            subjective=subjective,
        )
        return CitySite(progress=progress, checklist=checklist)

    @staticmethod
    def _holdings_existing_at(
        *, holdings: list[HoldingModel], records_df: pd.DataFrame, year_month: str
    ) -> list[HoldingModel]:
        """排除第一筆紀錄晚於選定月份的項目；從未錄過紀錄的項目保留（以初始市值計）。

        第一筆紀錄月份必須看全量紀錄：截斷後的紀錄看不到晚建立的項目，會誤判成從未錄過。
        """
        first_month_by_holding = records_df.groupby("holding_id")["year_month"].min()
        return [
            holding
            for holding in holdings
            if holding.holding_id not in first_month_by_holding.index
            or first_month_by_holding[holding.holding_id] <= year_month
        ]

    @staticmethod
    def _building_status(month_values: dict[str, float | None], month: str) -> str:
        """單月狀態：沒有該月的列為 absent，有列但留空為 unfilled，其餘為 present。"""
        if month not in month_values:
            return CITY_BUILDING_STATUS.ABSENT
        if month_values[month] is None:
            return CITY_BUILDING_STATUS.UNFILLED
        return CITY_BUILDING_STATUS.PRESENT

    def _buildings_at(
        self, *, year_month: str, timeline: CityTimeline, drift_rows: list[DriftRow]
    ) -> list[CityBuildingState]:
        """逐項目的選定月份狀態；偏離只掛在該類別且當月有建築（present）者。"""
        month_index = timeline.months.index(year_month)
        previous_month = timeline.months[month_index - 1] if month_index > 0 else None
        flagged_by_category = {row.category: row for row in drift_rows if row.needs_rebalance}

        buildings: list[CityBuildingState] = []
        for city_holding in timeline.holdings:
            values = city_holding.month_values
            status = self._building_status(values, year_month)
            value = values[year_month] if status == CITY_BUILDING_STATUS.PRESENT else None
            previous_status = (
                self._building_status(values, previous_month) if previous_month else None
            )
            delta = (
                value - values[previous_month]
                if value is not None and previous_status == CITY_BUILDING_STATUS.PRESENT
                else None
            )
            drift = (
                flagged_by_category.get(city_holding.category)
                if status == CITY_BUILDING_STATUS.PRESENT
                else None
            )
            buildings.append(
                CityBuildingState(
                    holding_id=city_holding.holding_id,
                    status=status,
                    value=value,
                    previous_month=previous_month,
                    previous_status=previous_status,
                    delta=delta,
                    drift=drift,
                )
            )
        return buildings

    @staticmethod
    def _house_purpose_categories(
        *, month_models: list[MonthlyRecordModel], holdings: list[HoldingModel]
    ) -> list[str]:
        """當月有非空市值的購屋用途資產所屬類別（遞增、不重複）。"""
        house_categories = {
            h.holding_id: h.category
            for h in holdings
            if h.purpose == HOLDING_PURPOSE.HOUSE
            and h.kind == HOLDING_KIND.ASSET
            and h.category is not None
        }
        return sorted(
            {
                house_categories[r.holding_id]
                for r in month_models
                if r.holding_id in house_categories and r.market_value is not None
            }
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
