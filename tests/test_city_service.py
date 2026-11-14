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
    DEFAULT_REBALANCE_THRESHOLD,
    HOLDING_KIND,
    HOLDING_PURPOSE,
    PROTOCOL_MIN_DATA_MONTHS,
)
from asset_lab.models.holding import HoldingModel
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
