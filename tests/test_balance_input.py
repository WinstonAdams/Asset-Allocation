"""BalanceInputService：活存/定存以餘額變動推算當月淨投入與連動重算（SC-092/093/094/103/106）。

BalanceInputService 為純運算 Service（無 I/O、無 Streamlit），直接餵虛構的
HoldingModel/MonthlyRecordModel 驗證，不連任何 DB。所有金額皆為虛構值。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    BALANCE_INPUT,
    COST_BASIS_INPUT,
    INPUT_MODE,
    PREMIUM_INPUT,
)
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import BalanceDerivation
from asset_lab.services.balance_input_service import BalanceInputService


def _service() -> BalanceInputService:
    return BalanceInputService(balance_categories=BALANCE_INPUT.CATEGORIES)


def _holding(
    *,
    category: str | None = ASSET_CATEGORIES.DEMAND_DEPOSIT,
    initial_market_value: float | None = 300000.0,
) -> HoldingModel:
    return HoldingModel(
        holding_id=1,
        name="活存",
        kind="asset",
        category=category,
        initial_market_value=initial_market_value,
    )


def _record(
    *, year_month: str, market_value: float | None, net_investment: float = 0.0
) -> MonthlyRecordModel:
    return MonthlyRecordModel(
        holding_id=1,
        year_month=year_month,
        market_value=market_value,
        net_investment=net_investment,
    )


def _three_records() -> list[MonthlyRecordModel]:
    return [
        _record(year_month="2026-04", market_value=500000.0, net_investment=200000.0),
        _record(year_month="2026-05", market_value=600000.0, net_investment=100000.0),
        _record(year_month="2026-06", market_value=580000.0, net_investment=-20000.0),
    ]


def _by_month(records: list[MonthlyRecordModel]) -> dict[str, MonthlyRecordModel]:
    return {r.year_month: r for r in records}


# === 常數：錄入方式對照 ===


@pytest.mark.scenario("SC-092")
def test_sc092_input_mode_maps_every_category_to_exactly_one_mode() -> None:
    """每個資產分類恰好對應一種錄入方式，三個分類集合互不重疊。"""
    sets = [COST_BASIS_INPUT.CATEGORIES, PREMIUM_INPUT.CATEGORIES, BALANCE_INPUT.CATEGORIES]

    assert set(INPUT_MODE.BY_ASSET_CATEGORY) == set(ASSET_CATEGORIES.ALL)
    assert sum(len(s) for s in sets) == len(set().union(*sets))
    assert INPUT_MODE.BY_ASSET_CATEGORY[ASSET_CATEGORIES.TW_STOCK] == INPUT_MODE.COST_BASIS
    assert INPUT_MODE.BY_ASSET_CATEGORY[ASSET_CATEGORIES.INSURANCE] == INPUT_MODE.PREMIUM
    assert INPUT_MODE.BY_ASSET_CATEGORY[ASSET_CATEGORIES.DEMAND_DEPOSIT] == INPUT_MODE.BALANCE
    assert INPUT_MODE.BY_ASSET_CATEGORY[ASSET_CATEGORIES.TIME_DEPOSIT] == INPUT_MODE.BALANCE


# === 餘額推算 ===


@pytest.mark.scenario("SC-092")
def test_sc092_first_record_uses_initial_market_value_as_previous() -> None:
    result = _service().derive(
        holding=_holding(), records=[], year_month="2026-04", balance=500000.0
    )

    assert result == BalanceDerivation(previous_balance=300000.0, net_investment=200000.0)


@pytest.mark.scenario("SC-092")
def test_sc092_plan_save_first_record_lands_balance_and_net_investment() -> None:
    planned = _service().plan_save(
        holding=_holding(), records=[], year_month="2026-04", balance=500000.0
    )

    assert len(planned) == 1
    saved = planned[0]
    assert (saved.holding_id, saved.year_month) == (1, "2026-04")
    assert saved.market_value == 500000.0
    assert saved.net_investment == 200000.0
    assert saved.total_cost is None
    assert saved.realized_income is None
    assert saved.cash_dividend is None


@pytest.mark.scenario("SC-092")
def test_sc092_subsequent_months_use_previous_month_balance() -> None:
    records = [_record(year_month="2026-04", market_value=500000.0, net_investment=200000.0)]
    service = _service()

    holding = _holding()

    may = service.derive(holding=holding, records=records, year_month="2026-05", balance=600000.0)
    records.append(_record(year_month="2026-05", market_value=600000.0, net_investment=100000.0))
    june = service.derive(holding=holding, records=records, year_month="2026-06", balance=450000.0)

    assert may.previous_balance == 500000.0
    assert may.net_investment == 100000.0
    assert june.net_investment == -150000.0


@pytest.mark.scenario("SC-092")
def test_sc092_time_deposit_same_rule_zero_change() -> None:
    holding = _holding(category=ASSET_CATEGORIES.TIME_DEPOSIT, initial_market_value=None)
    records = [_record(year_month="2026-04", market_value=1000000.0)]

    result = _service().derive(
        holding=holding, records=records, year_month="2026-05", balance=1000000.0
    )

    assert result.net_investment == 0.0


@pytest.mark.scenario("SC-092")
def test_sc092_zero_balance_means_full_withdrawal() -> None:
    records = [_record(year_month="2026-05", market_value=600000.0)]

    result = _service().derive(
        holding=_holding(), records=records, year_month="2026-06", balance=0.0
    )

    assert result.net_investment == -600000.0


@pytest.mark.scenario("SC-092")
def test_sc092_no_initial_value_and_no_records_previous_is_zero() -> None:
    result = _service().derive(
        holding=_holding(initial_market_value=None),
        records=[],
        year_month="2026-04",
        balance=100000.0,
    )

    assert result.previous_balance == 0.0
    assert result.net_investment == 100000.0


@pytest.mark.scenario("SC-092")
def test_sc092_non_balance_category_rejected() -> None:
    service = _service()
    holding = _holding(category=ASSET_CATEGORIES.TW_STOCK)

    with pytest.raises(DataValidationError):
        service.derive(holding=holding, records=[], year_month="2026-04", balance=1.0)
    with pytest.raises(DataValidationError):
        service.plan_save(holding=holding, records=[], year_month="2026-04", balance=1.0)
    with pytest.raises(DataValidationError):
        service.plan_delete(holding=holding, records=[], year_month="2026-04")


# === 前期餘額跳過空白列 ===


@pytest.mark.scenario("SC-093")
def test_sc093_previous_balance_skips_blank_balance_rows() -> None:
    records = [
        _record(year_month="2026-03", market_value=400000.0),
        _record(year_month="2026-04", market_value=None, net_investment=-50000.0),
    ]

    result = _service().derive(
        holding=_holding(), records=records, year_month="2026-05", balance=380000.0
    )

    assert result.previous_balance == 400000.0
    assert result.net_investment == -20000.0


@pytest.mark.scenario("SC-093")
def test_sc093_all_blank_falls_back_to_initial_market_value() -> None:
    records = [
        _record(year_month="2026-03", market_value=None, net_investment=10.0),
        _record(year_month="2026-04", market_value=None, net_investment=-50000.0),
    ]

    result = _service().derive(
        holding=_holding(), records=records, year_month="2026-05", balance=380000.0
    )

    assert result.previous_balance == 300000.0
    assert result.net_investment == 80000.0


@pytest.mark.scenario("SC-093")
def test_sc093_ignores_records_at_or_after_target_month_and_unsorted_input() -> None:
    records = [
        _record(year_month="2026-06", market_value=999999.0),
        _record(year_month="2026-03", market_value=400000.0),
        _record(year_month="2026-05", market_value=111111.0),
    ]

    result = _service().derive(
        holding=_holding(), records=records, year_month="2026-05", balance=380000.0
    )

    assert result.previous_balance == 400000.0


# === 連動重算 ===


@pytest.mark.scenario("SC-094")
def test_sc094_modify_recomputes_self_and_next_only() -> None:
    planned = _service().plan_save(
        holding=_holding(), records=_three_records(), year_month="2026-04", balance=520000.0
    )

    by_month = _by_month(planned)
    assert set(by_month) == {"2026-04", "2026-05"}
    assert by_month["2026-04"].market_value == 520000.0
    assert by_month["2026-04"].net_investment == 220000.0
    assert by_month["2026-05"].market_value == 600000.0
    assert by_month["2026-05"].net_investment == 80000.0


@pytest.mark.scenario("SC-094")
def test_sc094_delete_middle_recomputes_next_from_earlier_balance() -> None:
    planned = _service().plan_delete(
        holding=_holding(), records=_three_records(), year_month="2026-05"
    )

    assert len(planned) == 1
    assert planned[0].year_month == "2026-06"
    assert planned[0].net_investment == 80000.0
    assert planned[0].market_value == 580000.0


@pytest.mark.scenario("SC-094")
def test_sc094_resave_same_balance_does_not_rewrite_next() -> None:
    records = _three_records()
    records[1] = _record(year_month="2026-05", market_value=600000.0, net_investment=12345.0)

    planned = _service().plan_save(
        holding=_holding(), records=records, year_month="2026-04", balance=500000.0
    )

    assert [r.year_month for r in planned] == ["2026-04"]


@pytest.mark.scenario("SC-094")
def test_sc094_legacy_manual_next_record_is_overwritten_when_previous_changes() -> None:
    records = [
        _record(year_month="2026-04", market_value=500000.0, net_investment=200000.0),
        _record(year_month="2026-05", market_value=600000.0, net_investment=7777.0),
    ]

    planned = _service().plan_save(
        holding=_holding(), records=records, year_month="2026-04", balance=520000.0
    )

    assert _by_month(planned)["2026-05"].net_investment == 80000.0


@pytest.mark.scenario("SC-094")
def test_sc094_delete_earliest_next_falls_back_to_initial_market_value() -> None:
    planned = _service().plan_delete(
        holding=_holding(), records=_three_records(), year_month="2026-04"
    )

    assert len(planned) == 1
    assert planned[0].year_month == "2026-05"
    assert planned[0].net_investment == 300000.0


@pytest.mark.scenario("SC-094")
def test_sc094_blank_next_targets_first_following_row_with_balance() -> None:
    records = [
        _record(year_month="2026-04", market_value=500000.0, net_investment=200000.0),
        _record(year_month="2026-05", market_value=None, net_investment=-50000.0),
        _record(year_month="2026-06", market_value=580000.0, net_investment=-20000.0),
    ]

    planned = _service().plan_save(
        holding=_holding(), records=records, year_month="2026-04", balance=520000.0
    )

    by_month = _by_month(planned)
    assert set(by_month) == {"2026-04", "2026-06"}
    assert by_month["2026-06"].net_investment == 60000.0


@pytest.mark.scenario("SC-094")
def test_sc094_modify_last_record_only_updates_itself() -> None:
    planned = _service().plan_save(
        holding=_holding(), records=_three_records(), year_month="2026-06", balance=700000.0
    )

    assert [r.year_month for r in planned] == ["2026-06"]
    assert planned[0].net_investment == 100000.0


@pytest.mark.scenario("SC-094")
def test_sc094_insert_between_existing_records_recomputes_following() -> None:
    records = [
        _record(year_month="2026-04", market_value=500000.0, net_investment=200000.0),
        _record(year_month="2026-06", market_value=580000.0, net_investment=80000.0),
    ]

    planned = _service().plan_save(
        holding=_holding(), records=records, year_month="2026-05", balance=550000.0
    )

    by_month = _by_month(planned)
    assert by_month["2026-05"].net_investment == 50000.0
    assert by_month["2026-06"].net_investment == 30000.0


@pytest.mark.scenario("SC-094")
def test_sc094_delete_last_record_returns_empty_and_does_not_mutate_input() -> None:
    records = _three_records()
    snapshot = [r.model_copy() for r in records]

    planned = _service().plan_delete(holding=_holding(), records=records, year_month="2026-06")

    assert planned == []
    assert records == snapshot


# === 舊紀錄保留原值 ===


@pytest.mark.scenario("SC-106")
def test_sc106_new_save_leaves_legacy_records_untouched() -> None:
    records = [
        _record(year_month="2026-02", market_value=480000.0, net_investment=30000.0),
        _record(year_month="2026-03", market_value=500000.0, net_investment=20000.0),
    ]

    planned = _service().plan_save(
        holding=_holding(), records=records, year_month="2026-04", balance=520000.0
    )

    assert [r.year_month for r in planned] == ["2026-04"]
    assert planned[0].net_investment == 20000.0
    assert records[0].net_investment == 30000.0
    assert records[1].net_investment == 20000.0


# === 資金在項目間移動，活存端自動一出一進 ===


@pytest.mark.scenario("SC-103")
def test_sc103_balance_side_net_investment_offsets_transfer() -> None:
    records = [_record(year_month="2026-04", market_value=500000.0)]

    outflow = _service().derive(
        holding=_holding(), records=records, year_month="2026-05", balance=400000.0
    )
    inflow = _service().derive(
        holding=_holding(), records=records, year_month="2026-05", balance=550000.0
    )

    assert outflow.net_investment == -100000.0
    assert inflow.net_investment == 50000.0
