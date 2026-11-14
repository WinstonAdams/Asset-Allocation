"""CityService.build_timeline 測試：月份清單、進版位的項目、各月狀態與高度分母。

資料一律為虛構值。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pandas as pd
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    CITY_BUILDING_STATUS,
    DEFAULT_REBALANCE_THRESHOLD,
    HOLDING_KIND,
    HOLDING_PURPOSE,
    HOUSE_TRIGGER,
    PROTOCOL_LEVEL_CODE,
    PROTOCOL_MIN_DATA_MONTHS,
)
from asset_lab.core.utils import records_frame_to_models
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParams, SubjectiveTriggerModel
from asset_lab.models.protocol import ProtocolThresholds
from asset_lab.models.target import TargetAllocationModel
from asset_lab.services.affordability_service import AffordabilityService
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.city_service import CityService
from asset_lab.services.house_service import HouseService
from asset_lab.services.protocol_service import ProtocolService
from asset_lab.services.return_service import ReturnService

_COLUMNS = ["holding_id", "year_month", "market_value", "net_investment"]


def _service() -> CityService:
    return CityService(
        return_service=ReturnService(),
        protocol_service=ProtocolService(),
        allocation_service=AllocationService(),
        house_service=HouseService(),
        affordability_service=AffordabilityService(),
        min_data_months=PROTOCOL_MIN_DATA_MONTHS,
        rebalance_threshold=DEFAULT_REBALANCE_THRESHOLD,
    )


def _asset(
    holding_id: int,
    name: str,
    *,
    category: str = ASSET_CATEGORIES.TW_STOCK,
    purpose: str = HOLDING_PURPOSE.GENERAL,
    initial: float | None = None,
) -> HoldingModel:
    return HoldingModel(
        holding_id=holding_id,
        name=name,
        kind=HOLDING_KIND.ASSET,
        category=category,
        initial_market_value=initial,
        purpose=purpose,
    )


def _liability(holding_id: int, name: str) -> HoldingModel:
    return HoldingModel(holding_id=holding_id, name=name, kind=HOLDING_KIND.LIABILITY)


def _records(rows: list[tuple[int, str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(
        [(hid, ym, value, 0.0) for hid, ym, value in rows],
        columns=_COLUMNS,
    )


def _by_id(timeline, holding_id: int):
    return next(h for h in timeline.holdings if h.holding_id == holding_id)


@pytest.mark.scenario("SC-133")
def test_sc133_assets_and_liability_with_records_enter_layout() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(2, "活存乙", category=ASSET_CATEGORIES.DEMAND_DEPOSIT),
        _liability(3, "房貸丙"),
    ]
    records = _records([(1, "2026-08", 100.0), (2, "2026-08", 50.0), (3, "2026-08", 300.0)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert [h.holding_id for h in timeline.holdings] == [1, 2, 3]
    assert _by_id(timeline, 3).kind == HOLDING_KIND.LIABILITY
    assert _by_id(timeline, 3).category is None
    assert _by_id(timeline, 1).category == ASSET_CATEGORIES.TW_STOCK


@pytest.mark.scenario("SC-133")
def test_sc133_blank_only_holding_still_enters_layout() -> None:
    holdings = [_asset(1, "台股ETF甲"), _asset(2, "活存乙")]
    records = _records([(1, "2026-08", 100.0), (2, "2026-08", None)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    blank = _by_id(timeline, 2)
    assert blank.month_values == {"2026-08": None}
    assert blank.peak_value == 0


@pytest.mark.scenario("SC-133")
def test_sc133_holdings_sorted_by_id_regardless_of_input_order() -> None:
    holdings = [_asset(5, "乙"), _asset(2, "甲")]
    records = _records([(5, "2026-08", 1.0), (2, "2026-08", 2.0)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert [h.holding_id for h in timeline.holdings] == [2, 5]


@pytest.mark.scenario("SC-134")
def test_sc134_house_purpose_holding_has_no_building() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(4, "定存丁", category=ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
    ]
    records = _records([(1, "2026-08", 100.0), (4, "2026-08", 2_000_000.0)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert [h.holding_id for h in timeline.holdings] == [1]
    # 購屋項目的 200 萬不進高度分母
    assert timeline.max_asset_value == 100.0


@pytest.mark.scenario("SC-134")
def test_sc134_unmarking_house_purpose_brings_building_back() -> None:
    records = _records([(4, "2026-08", 2_000_000.0)])
    as_house = _asset(4, "定存丁", purpose=HOLDING_PURPOSE.HOUSE)
    as_general = _asset(4, "定存丁", purpose=HOLDING_PURPOSE.GENERAL)

    before = _service().build_timeline(holdings=[as_house], records_df=records)
    after = _service().build_timeline(holdings=[as_general], records_df=records)

    assert before.holdings == []
    assert [h.holding_id for h in after.holdings] == [4]


@pytest.mark.scenario("SC-134")
def test_sc134_marking_existing_holding_as_house_removes_building() -> None:
    records = _records([(2, "2026-08", 50.0)])
    general = _asset(2, "活存乙", category=ASSET_CATEGORIES.DEMAND_DEPOSIT)
    house = _asset(
        2, "活存乙", category=ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE
    )

    assert len(_service().build_timeline(holdings=[general], records_df=records).holdings) == 1
    assert _service().build_timeline(holdings=[house], records_df=records).holdings == []


@pytest.mark.scenario("SC-135")
def test_sc135_holding_without_any_record_not_in_layout() -> None:
    holdings = [_asset(1, "台股ETF甲"), _asset(5, "美股ETF戊", initial=500_000.0)]
    records = _records([(1, "2026-08", 100.0)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert [h.holding_id for h in timeline.holdings] == [1]


@pytest.mark.scenario("SC-135")
def test_sc135_first_record_later_enters_layout_with_earlier_months_absent() -> None:
    holdings = [_asset(1, "台股ETF甲"), _asset(5, "美股ETF戊", initial=500_000.0)]
    records = _records([(1, "2026-08", 100.0), (1, "2026-09", 110.0), (5, "2026-09", 520_000.0)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    late = _by_id(timeline, 5)
    assert late.month_values == {"2026-09": 520_000.0}
    assert "2026-08" not in late.month_values


@pytest.mark.scenario("SC-136")
def test_sc136_months_ascending_and_latest_includes_liability_and_house_only_month() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _liability(3, "房貸丙"),
        _asset(4, "定存丁", purpose=HOLDING_PURPOSE.HOUSE),
    ]
    records = _records(
        [
            (1, "2026-09", 1.0),  # 刻意亂序
            (1, "2026-06", 1.0),
            (1, "2026-07", 1.0),
            (3, "2026-09", 300.0),
            (4, "2026-09", 200.0),
        ]
    )
    # 2026-09 只剩負債與購屋項目：移除甲在該月的列
    records = records[~((records.holding_id == 1) & (records.year_month == "2026-09"))]

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert timeline.months == ["2026-06", "2026-07", "2026-09"]
    assert timeline.latest_month == "2026-09"


@pytest.mark.scenario("SC-136")
def test_sc136_no_records_gives_empty_timeline() -> None:
    timeline = _service().build_timeline(holdings=[_asset(1, "甲")], records_df=_records([]))

    assert timeline.months == []
    assert timeline.latest_month is None
    assert timeline.holdings == []
    assert timeline.max_asset_value == 0
    assert timeline.max_liability_value == 0


@pytest.mark.scenario("SC-139")
def test_sc139_month_values_distinguish_present_blank_and_absent() -> None:
    deposit_category = ASSET_CATEGORIES.DEMAND_DEPOSIT
    holdings = [_asset(1, "台股ETF甲"), _asset(2, "活存乙", category=deposit_category)]
    records = _records(
        [
            (1, "2026-06", 10.0),
            (1, "2026-07", 10.0),
            (1, "2026-08", 10.0),
            (2, "2026-07", 300_000.0),
            (2, "2026-08", None),
        ]
    )

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    deposit = _by_id(timeline, 2)
    assert "2026-06" not in deposit.month_values  # 無此項目
    assert deposit.month_values["2026-07"] == 300_000.0  # 有值
    assert "2026-08" in deposit.month_values and deposit.month_values["2026-08"] is None  # 未填


@pytest.mark.scenario("SC-139")
def test_sc139_exited_holding_later_months_have_no_key() -> None:
    holdings = [_asset(1, "台股ETF甲"), _asset(2, "活存乙")]
    records = _records([(1, "2026-06", 1.0), (1, "2026-07", 1.0), (2, "2026-06", 5.0)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert set(_by_id(timeline, 2).month_values) == {"2026-06"}


@pytest.mark.scenario("SC-140")
def test_sc140_blank_month_is_none_not_carried_forward() -> None:
    holdings = [_asset(1, "台股ETF甲")]
    records = _records([(1, "2026-07", 1_200_000.0), (1, "2026-08", None)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert _by_id(timeline, 1).month_values == {"2026-07": 1_200_000.0, "2026-08": None}


@pytest.mark.scenario("SC-140")
def test_sc140_holding_blank_from_first_appearance() -> None:
    holdings = [_asset(1, "台股ETF甲"), _asset(2, "活存乙")]
    records = _records([(1, "2026-08", 100.0), (2, "2026-08", None)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert _by_id(timeline, 2).month_values == {"2026-08": None}


@pytest.mark.scenario("SC-141")
def test_sc141_blank_month_does_not_participate_in_peak_or_denominator() -> None:
    holdings = [_asset(1, "台股ETF甲"), _asset(2, "活存乙")]
    records = _records(
        [
            (1, "2026-06", 4_000_000.0),
            (1, "2026-07", 1_000_000.0),
            (1, "2026-08", None),
            (2, "2026-08", 500_000.0),
        ]
    )

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert _by_id(timeline, 1).peak_value == 4_000_000.0
    assert timeline.max_asset_value == 4_000_000.0


@pytest.mark.scenario("SC-141")
def test_sc141_all_blank_holding_keeps_lot_with_zero_peak_and_not_in_denominator() -> None:
    holdings = [_asset(1, "台股ETF甲"), _asset(2, "活存乙"), _liability(3, "房貸丙")]
    records = _records(
        [(1, "2026-08", 100.0), (2, "2026-08", None), (2, "2026-09", None), (3, "2026-08", None)]
    )

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert _by_id(timeline, 2).peak_value == 0
    assert _by_id(timeline, 3).peak_value == 0
    assert timeline.max_asset_value == 100.0
    assert timeline.max_liability_value == 0


@pytest.mark.scenario("SC-141")
def test_sc141_denominators_split_by_kind() -> None:
    holdings = [
        _asset(1, "甲"),
        _asset(2, "乙"),
        _liability(3, "房貸丙"),
        _liability(4, "信貸"),
    ]
    records = _records(
        [(1, "2026-08", 100.0), (2, "2026-08", 700.0), (3, "2026-08", 900.0), (4, "2026-08", 50.0)]
    )

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert timeline.max_asset_value == 700.0
    assert timeline.max_liability_value == 900.0


@pytest.mark.scenario("SC-144")
def test_sc144_house_holdings_never_affect_layout_or_denominator() -> None:
    # 工地口徑的歷史月份截斷屬 frame_at；此處驗證時間軸端：
    # 從未錄紀錄的購屋項目、晚建立的購屋項目都不進版位、不影響分母
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(6, "定存己", purpose=HOLDING_PURPOSE.HOUSE, initial=600_000.0),
        _asset(7, "定存庚", purpose=HOLDING_PURPOSE.HOUSE),
    ]
    records = _records([(1, "2026-06", 100.0), (7, "2026-08", 900_000.0)])

    timeline = _service().build_timeline(holdings=holdings, records_df=records)

    assert [h.holding_id for h in timeline.holdings] == [1]
    assert timeline.max_asset_value == 100.0
    # 定存庚的紀錄月份仍屬月份清單（最新月結口徑含購屋項目）
    assert timeline.months == ["2026-06", "2026-08"]


# ---------------------------------------------------------------------------
# frame_at
# ---------------------------------------------------------------------------

_THRESHOLDS = ProtocolThresholds(l1=10.0, l2=20.0, l3=30.0)
_PARAMS = HouseParams(
    target_total_price=10_000_000.0,
    target_year=2030,
    monthly_after_tax_income=100_000.0,
    income_threshold=80_000.0,
    cash_floor=500_000.0,
    down_payment_ratio=30.0,
    payment_cap_ratio=33.0,
    test_annual_rate=2.5,
    loan_years=30,
)
_SUBJECTIVE = [SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True)]
_CURRENT_YEAR = 2026


def _frame(
    holdings: list[HoldingModel],
    records: pd.DataFrame,
    year_month: str,
    *,
    targets: list[TargetAllocationModel] | None = None,
    service: CityService | None = None,
):
    service = service or _service()
    timeline = service.build_timeline(holdings=holdings, records_df=records)
    return service.frame_at(
        year_month=year_month,
        timeline=timeline,
        holdings=holdings,
        records_df=records,
        thresholds=_THRESHOLDS,
        house_params=_PARAMS,
        subjective=_SUBJECTIVE,
        targets=targets or [],
        current_year=_CURRENT_YEAR,
    )


def _building(frame, holding_id: int):
    # buildings 與 timeline.holdings 同順序；以 holding_id 取用
    return next(b for b in frame.buildings if b.holding_id == holding_id)


@pytest.mark.scenario("SC-143")
def test_sc143_historical_month_uses_house_value_of_that_month() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(4, "定存丁", category=ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
    ]
    records = _records(
        [
            (1, "2026-06", 50.0),
            (4, "2026-06", 1_000_000.0),
            (1, "2026-09", 60.0),
            (4, "2026-09", 1_800_000.0),
        ]
    )

    frame = _frame(holdings, records, "2026-06")

    assert frame.is_latest is False
    assert frame.site.progress.bucket_value == 1_000_000.0
    assert frame.site.progress.progress_pct == pytest.approx(1_000_000 / 3_000_000 * 100)


@pytest.mark.scenario("SC-143")
def test_sc143_latest_month_uses_latest_house_value_and_is_latest() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(4, "定存丁", category=ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
    ]
    records = _records(
        [
            (1, "2026-06", 50.0),
            (4, "2026-06", 1_000_000.0),
            (1, "2026-09", 60.0),
            (4, "2026-09", 1_800_000.0),
        ]
    )

    frame = _frame(holdings, records, "2026-09")

    assert frame.is_latest is True
    assert frame.site.progress.bucket_value == 1_800_000.0
    assert frame.site.progress.progress_pct == pytest.approx(60.0)


@pytest.mark.scenario("SC-143")
def test_sc143_target_always_uses_current_params() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(4, "定存丁", category=ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
    ]
    records = _records(
        [(1, "2026-06", 50.0), (4, "2026-06", 1_000_000.0), (1, "2026-09", 60.0)]
    )

    historical = _frame(holdings, records, "2026-06")
    latest = _frame(holdings, records, "2026-09")

    assert historical.site.progress.target_amount == 3_000_000.0
    assert latest.site.progress.target_amount == 3_000_000.0
    assert [c.key for c in historical.site.checklist.conditions] == list(HOUSE_TRIGGER.ALL)


@pytest.mark.scenario("SC-144")
def test_sc144_never_recorded_house_holding_counts_initial_value_every_month() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(
            6,
            "定存己",
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            purpose=HOLDING_PURPOSE.HOUSE,
            initial=600_000.0,
        ),
    ]
    records = _records([(1, "2026-06", 50.0), (1, "2026-07", 60.0), (1, "2026-08", 70.0)])

    for month in ("2026-06", "2026-07", "2026-08"):
        assert _frame(holdings, records, month).site.progress.bucket_value == 600_000.0


@pytest.mark.scenario("SC-144")
def test_sc144_late_house_holding_not_counted_before_first_record() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(
            6,
            "定存己",
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            purpose=HOLDING_PURPOSE.HOUSE,
            initial=600_000.0,
        ),
        _asset(
            7,
            "定存庚",
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            purpose=HOLDING_PURPOSE.HOUSE,
            initial=900_000.0,
        ),
    ]
    records = _records(
        [
            (1, "2026-06", 50.0),
            (1, "2026-07", 60.0),
            (1, "2026-08", 70.0),
            (7, "2026-08", 900_000.0),
        ]
    )

    assert _frame(holdings, records, "2026-06").site.progress.bucket_value == 600_000.0
    assert _frame(holdings, records, "2026-07").site.progress.bucket_value == 600_000.0
    assert _frame(holdings, records, "2026-08").site.progress.bucket_value == 1_500_000.0


def _twr_holdings_and_records() -> tuple[list[HoldingModel], pd.DataFrame]:
    values = [100.0, 120.0, 150.0, 180.0, 200.0, 190.0, 180.0, 170.0, 150.0]
    months = [f"2026-{m:02d}" for m in range(1, 10)]
    holdings = [_asset(1, "台股ETF甲")]
    return holdings, _records([(1, ym, v) for ym, v in zip(months, values, strict=True)])


@pytest.mark.scenario("SC-149")
def test_sc149_each_month_weather_judged_on_data_up_to_that_month() -> None:
    holdings, records = _twr_holdings_and_records()

    june = _frame(holdings, records, "2026-06").weather
    september = _frame(holdings, records, "2026-09").weather

    assert june.drawdown == pytest.approx(-0.05)
    assert june.level_code == PROTOCOL_LEVEL_CODE.L0
    assert september.drawdown == pytest.approx(-0.25)
    assert september.level_code == PROTOCOL_LEVEL_CODE.L2


@pytest.mark.scenario("SC-149")
def test_sc149_fewer_than_min_months_before_selected_month_is_neutral() -> None:
    holdings, records = _twr_holdings_and_records()

    weather = _frame(holdings, records, "2026-02").weather

    assert weather.status == "insufficient_data"
    assert weather.level_code == PROTOCOL_LEVEL_CODE.L0
    assert weather.drawdown is None


def _drift_holdings() -> list[HoldingModel]:
    return [
        _asset(1, "台股ETF甲"),
        _asset(2, "美股ETF辛", category=ASSET_CATEGORIES.US_STOCK),
    ]


_DRIFT_TARGETS = [
    TargetAllocationModel(category=ASSET_CATEGORIES.TW_STOCK, target_weight=40.0),
    TargetAllocationModel(category=ASSET_CATEGORIES.US_STOCK, target_weight=30.0),
]


@pytest.mark.scenario("SC-150")
def test_sc150_drift_only_marks_building_of_that_category() -> None:
    records = _records([(1, "2026-08", 700.0), (2, "2026-08", 300.0)])

    frame = _frame(_drift_holdings(), records, "2026-08", targets=_DRIFT_TARGETS)

    tw = _building(frame, 1)
    assert tw.drift is not None
    assert tw.drift.category == ASSET_CATEGORIES.TW_STOCK
    assert tw.drift.needs_rebalance is True
    assert _building(frame, 2).drift is None
    assert len(frame.drift_rows) == 2


@pytest.mark.scenario("SC-150")
def test_sc150_category_with_only_house_purpose_holding_marks_no_building() -> None:
    holdings = _drift_holdings() + [
        _asset(4, "定存丁", category=ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE)
    ]
    records = _records([(1, "2026-08", 350.0), (2, "2026-08", 350.0), (4, "2026-08", 300.0)])
    targets = [
        TargetAllocationModel(category=ASSET_CATEGORIES.TW_STOCK, target_weight=35.0),
        TargetAllocationModel(category=ASSET_CATEGORIES.US_STOCK, target_weight=35.0),
        TargetAllocationModel(category=ASSET_CATEGORIES.TIME_DEPOSIT, target_weight=10.0),
    ]

    frame = _frame(holdings, records, "2026-08", targets=targets)

    time_deposit = next(r for r in frame.drift_rows if r.category == ASSET_CATEGORIES.TIME_DEPOSIT)
    assert time_deposit.needs_rebalance is True
    assert all(b.drift is None for b in frame.buildings)
    assert frame.house_purpose_categories == [ASSET_CATEGORIES.TIME_DEPOSIT]


@pytest.mark.scenario("SC-150")
def test_sc150_absent_building_in_flagged_category_gets_no_drift() -> None:
    holdings = [_asset(1, "台股ETF乙"), _asset(2, "美股ETF辛", category=ASSET_CATEGORIES.US_STOCK)]
    records = _records([(1, "2026-07", 100.0), (2, "2026-07", 100.0), (2, "2026-08", 100.0)])

    frame = _frame(holdings, records, "2026-08", targets=_DRIFT_TARGETS)

    flagged = next(r for r in frame.drift_rows if r.category == ASSET_CATEGORIES.TW_STOCK)
    assert flagged.needs_rebalance is True
    assert _building(frame, 1).status == CITY_BUILDING_STATUS.ABSENT
    assert _building(frame, 1).drift is None


@pytest.mark.scenario("SC-150")
def test_sc150_unfilled_building_in_flagged_category_gets_no_drift() -> None:
    holdings = [_asset(1, "台股ETF乙"), _asset(2, "美股ETF辛", category=ASSET_CATEGORIES.US_STOCK)]
    records = _records([(1, "2026-08", None), (2, "2026-08", 100.0)])

    frame = _frame(holdings, records, "2026-08", targets=_DRIFT_TARGETS)

    assert _building(frame, 1).status == CITY_BUILDING_STATUS.UNFILLED
    assert _building(frame, 1).drift is None


@pytest.mark.scenario("SC-150")
def test_sc150_house_purpose_categories_only_when_non_blank_value_that_month() -> None:
    holdings = _drift_holdings() + [
        _asset(4, "定存丁", category=ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE)
    ]
    records = _records(
        [(1, "2026-07", 100.0), (4, "2026-07", 500.0), (1, "2026-08", 100.0), (4, "2026-08", None)]
    )

    assert _frame(holdings, records, "2026-07").house_purpose_categories == [
        ASSET_CATEGORIES.TIME_DEPOSIT
    ]
    assert _frame(holdings, records, "2026-08").house_purpose_categories == []


@pytest.mark.scenario("SC-150")
def test_sc150_historical_drift_uses_that_month_weights_and_current_targets() -> None:
    records = _records(
        [(1, "2026-06", 400.0), (2, "2026-06", 600.0), (1, "2026-08", 700.0), (2, "2026-08", 300.0)]
    )

    june = _frame(_drift_holdings(), records, "2026-06", targets=_DRIFT_TARGETS)

    tw = next(r for r in june.drift_rows if r.category == ASSET_CATEGORIES.TW_STOCK)
    assert tw.current_weight == pytest.approx(40.0)
    assert tw.target_weight == 40.0
    assert tw.needs_rebalance is False
    assert _building(june, 1).drift is None


@pytest.mark.scenario("SC-145")
def test_sc145_latest_month_matches_existing_page_results() -> None:
    holdings = [
        _asset(1, "台股ETF甲"),
        _asset(2, "美股ETF辛", category=ASSET_CATEGORIES.US_STOCK),
        _asset(3, "活存乙", category=ASSET_CATEGORIES.DEMAND_DEPOSIT),
        _asset(4, "定存丁", category=ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
        _liability(5, "房貸丙"),
    ]
    history = [
        (ym, v)
        for ym, v in zip(
            ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"],
            [100.0, 130.0, 150.0, 120.0, 140.0],
            strict=True,
        )
    ]
    rows: list[tuple[int, str, float | None]] = []
    for ym, v in history:
        rows += [
            (1, ym, v * 1000),
            (2, ym, 80_000.0),
            (3, ym, 500_000.0),
            (4, ym, 1_200_000.0 if ym == "2026-09" else 900_000.0),
            (5, ym, 2_000_000.0),
        ]
    records = _records(rows)
    targets = [
        TargetAllocationModel(category=ASSET_CATEGORIES.TW_STOCK, target_weight=10.0),
        TargetAllocationModel(category=ASSET_CATEGORIES.US_STOCK, target_weight=5.0),
    ]
    service = _service()

    frame = _frame(holdings, records, "2026-09", targets=targets, service=service)

    # 總覽頁：全序列累積 TWR 直接判定
    series = ReturnService().cumulative_twr_series(range_df=records, holdings=holdings)
    expected_weather = ProtocolService().assess(
        series=series, thresholds=_THRESHOLDS, min_data_months=PROTOCOL_MIN_DATA_MONTHS
    )
    assert frame.weather == expected_weather

    # 買房頁：全量紀錄直接編排
    house = HouseService()
    month_records = records_frame_to_models(records)
    bucket = house.bucket_value(month_records=month_records, holdings=holdings)
    reserve = house.cash_reserve_value(month_records=month_records, holdings=holdings)
    forward = AffordabilityService().payment_for_price(
        total_price=_PARAMS.target_total_price,
        down_payment_ratio_pct=_PARAMS.down_payment_ratio,
        test_annual_rate_pct=_PARAMS.test_annual_rate,
        loan_years=_PARAMS.loan_years,
        monthly_income=_PARAMS.monthly_after_tax_income,
    )
    expected_progress = house.bucket_progress(
        bucket_value=bucket, params=_PARAMS, current_year=_CURRENT_YEAR
    )
    expected_checklist = house.assess_triggers(
        params=_PARAMS,
        bucket_value=bucket,
        cash_reserve_value=reserve,
        forward_result=forward,
        subjective=_SUBJECTIVE,
    )
    assert frame.site.progress.progress_pct == expected_progress.progress_pct
    assert frame.site.checklist.met_count == expected_checklist.met_count

    # 資產配置頁：最新月快照直接算偏離
    allocation = AllocationService()
    latest_rows = [r for r in month_records if r.year_month == "2026-09"]
    snapshot = allocation.snapshot(month_records=latest_rows, holdings=holdings, by="category")
    expected_drift = allocation.compute_drift(
        snapshot=snapshot, targets=targets, threshold=DEFAULT_REBALANCE_THRESHOLD
    )
    assert frame.drift_rows == expected_drift


@pytest.mark.scenario("SC-140")
def test_sc140_building_state_status_value_and_delta() -> None:
    holdings = [_asset(1, "甲"), _asset(2, "乙")]
    records = _records(
        [
            (1, "2026-06", 100.0),
            (2, "2026-06", 50.0),
            (1, "2026-07", 130.0),
            (2, "2026-07", None),
            (1, "2026-08", None),
        ]
    )

    july = _frame(holdings, records, "2026-07")
    august = _frame(holdings, records, "2026-08")
    june = _frame(holdings, records, "2026-06")

    assert [b.holding_id for b in july.buildings] == [1, 2]
    assert _building(july, 1).status == CITY_BUILDING_STATUS.PRESENT
    assert _building(july, 1).value == 130.0
    assert _building(july, 1).previous_month == "2026-06"
    assert _building(july, 1).delta == 30.0
    assert _building(july, 2).status == CITY_BUILDING_STATUS.UNFILLED
    assert _building(july, 2).value is None
    assert _building(july, 2).delta is None
    assert _building(august, 1).previous_status == CITY_BUILDING_STATUS.PRESENT
    assert _building(august, 1).delta is None
    assert _building(august, 2).status == CITY_BUILDING_STATUS.ABSENT
    assert _building(june, 1).previous_month is None
    assert _building(june, 1).previous_status is None
    assert _building(june, 1).delta is None


@pytest.mark.scenario("SC-143")
def test_frame_at_rejects_month_not_in_timeline() -> None:
    holdings, records = _twr_holdings_and_records()

    with pytest.raises(ValueError):
        _frame(holdings, records, "2030-01")
