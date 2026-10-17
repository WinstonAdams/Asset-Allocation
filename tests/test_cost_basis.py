"""CostBasisService：股票/ETF 依總成本與已實現收益推算當月淨投入（SC-074~078）。

CostBasisService 為純運算 Service（無 I/O、無 Streamlit），直接餵虛構的
HoldingModel/MonthlyRecordModel 驗證，不連任何 DB。所有金額皆為虛構值。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, COST_BASIS_INPUT
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.services.cost_basis_service import CostBasisService


def _holding(
    *,
    holding_id: int = 1,
    name: str = "台積電",
    category: str | None = ASSET_CATEGORIES.TW_STOCK,
    initial_cost: float | None = 0.0,
) -> HoldingModel:
    """建立一個股票/ETF 分類的資產項目主檔（供 derive 系列測試共用）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=name,
        kind="asset",
        category=category,
        initial_market_value=initial_cost,
        initial_cost=initial_cost,
    )


def _record(
    *,
    holding_id: int = 1,
    year_month: str,
    market_value: float | None = None,
    net_investment: float = 0.0,
    total_cost: float | None = None,
    realized_income: float | None = None,
    cash_dividend: float | None = None,
) -> MonthlyRecordModel:
    """建立一筆月度紀錄（供 derive 系列測試組出前期紀錄序列）。"""
    return MonthlyRecordModel(
        holding_id=holding_id,
        year_month=year_month,
        market_value=market_value,
        net_investment=net_investment,
        total_cost=total_cost,
        realized_income=realized_income,
        cash_dividend=cash_dividend,
    )


def _approx(value: float, expected: float, abs_: float = 1e-6) -> bool:
    """以浮點容差比較試算結果數值。"""
    return value == pytest.approx(expected, abs=abs_)


@pytest.fixture
def service() -> CostBasisService:
    return CostBasisService(cost_basis_categories=COST_BASIS_INPUT.CATEGORIES)


class TestUsesCostBasis:
    """uses_cost_basis：判斷項目是否走總成本推算（SC-074 邊界：分類判斷）。"""

    @pytest.mark.scenario("SC-074")
    @pytest.mark.parametrize(
        "category, expected",
        [
            (ASSET_CATEGORIES.TW_STOCK, True),
            (ASSET_CATEGORIES.US_STOCK, True),
            (ASSET_CATEGORIES.DEMAND_DEPOSIT, False),
            (ASSET_CATEGORIES.TIME_DEPOSIT, False),
            (ASSET_CATEGORIES.INSURANCE, False),
            (None, False),
        ],
    )
    def test_sc074_uses_cost_basis_only_for_stock_categories(
        self, service: CostBasisService, category: str | None, expected: bool
    ):
        holding = _holding(category=category)
        assert service.uses_cost_basis(holding=holding) is expected


class TestDeriveHappyPath:
    """derive：股票/ETF 依總成本與前期總成本推算當月淨投入（SC-074）。"""

    @pytest.mark.scenario("SC-074")
    def test_sc074_first_record_uses_initial_cost_as_previous_total_cost(
        self, service: CostBasisService
    ):
        holding = _holding(initial_cost=300_000)

        result = service.derive(
            holding=holding,
            records=[],
            year_month="2026-05",
            total_cost=350_000,
            realized_pnl=0,
            cash_dividend=0.0,
        )

        assert _approx(result.previous_total_cost, 300_000)
        assert result.is_transition_estimate is False
        assert _approx(result.net_investment, 50_000)

    @pytest.mark.scenario("SC-074")
    def test_sc074_subsequent_record_uses_previous_record_total_cost(
        self, service: CostBasisService
    ):
        holding = _holding(initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05",
                market_value=400_000,
                net_investment=50_000,
                total_cost=350_000,
                realized_income=0,
            ),
        ]

        result = service.derive(
            holding=holding,
            records=records,
            year_month="2026-06",
            total_cost=400_000,
            realized_pnl=0,
            cash_dividend=0.0,
        )

        assert _approx(result.previous_total_cost, 350_000)
        assert result.is_transition_estimate is False
        assert _approx(result.net_investment, 50_000)

    @pytest.mark.scenario("SC-074")
    def test_sc074_nonzero_realized_income_deducted_from_difference(
        self, service: CostBasisService
    ):
        holding = _holding(initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05",
                market_value=400_000,
                net_investment=50_000,
                total_cost=350_000,
                realized_income=0,
            ),
            _record(
                year_month="2026-06",
                market_value=420_000,
                net_investment=50_000,
                total_cost=400_000,
                realized_income=0,
            ),
        ]

        result = service.derive(
            holding=holding,
            records=records,
            year_month="2026-07",
            total_cost=380_000,
            realized_pnl=15_000,
            cash_dividend=0.0,
        )

        assert _approx(result.previous_total_cost, 400_000)
        assert _approx(result.net_investment, -35_000)

    @pytest.mark.scenario("SC-074")
    def test_sc074_negative_realized_income_added_back_into_net_investment(
        self, service: CostBasisService
    ):
        holding = _holding(initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05",
                market_value=400_000,
                net_investment=50_000,
                total_cost=350_000,
                realized_income=0,
            ),
            _record(
                year_month="2026-06",
                market_value=420_000,
                net_investment=50_000,
                total_cost=400_000,
                realized_income=0,
            ),
        ]

        result = service.derive(
            holding=holding,
            records=records,
            year_month="2026-07",
            total_cost=380_000,
            realized_pnl=-5_000,
            cash_dividend=0.0,
        )

        assert _approx(result.previous_total_cost, 400_000)
        assert _approx(result.net_investment, -15_000)

    @pytest.mark.scenario("SC-074")
    def test_sc074_first_record_with_unset_initial_cost_treats_none_as_zero(
        self, service: CostBasisService
    ):
        holding = _holding(initial_cost=None)

        result = service.derive(
            holding=holding,
            records=[],
            year_month="2026-05",
            total_cost=10_000,
            realized_pnl=0,
            cash_dividend=0.0,
        )

        assert _approx(result.previous_total_cost, 0.0)
        assert _approx(result.net_investment, 10_000)

    @pytest.mark.scenario("SC-074")
    def test_sc074_derive_rejects_holding_not_using_cost_basis(self, service: CostBasisService):
        holding = _holding(category=ASSET_CATEGORIES.DEMAND_DEPOSIT)

        with pytest.raises(DataValidationError):
            service.derive(
                holding=holding,
                records=[],
                year_month="2026-05",
                total_cost=10_000,
                realized_pnl=0,
                cash_dividend=0.0,
            )


class TestDeriveTransitionEstimate:
    """derive：前一筆為本功能上線前建立的舊制列時，以初始成本加總淨投入估算（SC-075）。"""

    @pytest.mark.scenario("SC-075")
    def test_sc075_previous_legacy_record_estimates_from_initial_cost_and_net_investment_sum(
        self, service: CostBasisService
    ):
        holding = _holding(name="鴻海", initial_cost=200_000)
        records = [
            _record(year_month="2026-02", market_value=None, net_investment=30_000),
            _record(year_month="2026-03", market_value=None, net_investment=20_000),
        ]

        result = service.derive(
            holding=holding,
            records=records,
            year_month="2026-04",
            total_cost=280_000,
            realized_pnl=0,
            cash_dividend=0.0,
        )

        assert _approx(result.previous_total_cost, 250_000)
        assert result.is_transition_estimate is True
        assert _approx(result.net_investment, 30_000)


class TestDeriveLiquidation:
    """derive：清倉月總成本與現值皆填 0，推算淨投入等於負的賣出實收（SC-076）。"""

    @pytest.mark.scenario("SC-076")
    def test_sc076_liquidation_month_net_investment_equals_negative_sale_proceeds(
        self, service: CostBasisService
    ):
        holding = _holding(name="聯發科", initial_cost=0)
        records = [
            _record(
                year_month="2026-05",
                market_value=350_000,
                net_investment=0,
                total_cost=350_000,
                realized_income=0,
            ),
        ]

        result = service.derive(
            holding=holding,
            records=records,
            year_month="2026-06",
            total_cost=0,
            realized_pnl=50_000,
            cash_dividend=0.0,
        )

        assert _approx(result.previous_total_cost, 350_000)
        assert _approx(result.net_investment, -400_000)


def _net_investment_by_year_month(plan: list[MonthlyRecordModel]) -> dict[str, float]:
    """把 plan_save/plan_delete 回傳的列攤成 {year_month: net_investment}，方便斷言。"""
    return {record.year_month: record.net_investment for record in plan}


class TestPlanSaveRecalculatesImmediateFollowingRecord:
    """plan_save：修改某月總成本後，只有緊接的下一筆新制列淨投入跟著重算（SC-077）。"""

    @pytest.mark.scenario("SC-077")
    def test_sc077_edit_earlier_record_recalculates_only_immediate_following_record(
        self, service: CostBasisService
    ):
        holding = _holding(name="中華電", initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05", net_investment=50_000, total_cost=350_000, realized_income=0
            ),
            _record(
                year_month="2026-06", net_investment=50_000, total_cost=400_000, realized_income=0
            ),
            _record(
                year_month="2026-07", net_investment=20_000, total_cost=420_000, realized_income=0
            ),
        ]

        plan = service.plan_save(
            holding=holding,
            records=records,
            year_month="2026-05",
            market_value=420_000,
            total_cost=360_000,
            realized_pnl=0,
            cash_dividend=0.0,
        )

        by_ym = _net_investment_by_year_month(plan)
        assert set(by_ym) == {"2026-05", "2026-06"}
        assert _approx(by_ym["2026-05"], 60_000)
        assert _approx(by_ym["2026-06"], 40_000)

    @pytest.mark.scenario("SC-077")
    def test_sc077_save_most_recent_record_returns_only_saved_row_when_nothing_follows(
        self, service: CostBasisService
    ):
        """邊界自審：異動月份之後沒有任何列時，往後掃描不應該產生任何額外列。"""
        holding = _holding(name="中華電", initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05", net_investment=50_000, total_cost=350_000, realized_income=0
            ),
        ]

        plan = service.plan_save(
            holding=holding,
            records=records,
            year_month="2026-06",
            market_value=430_000,
            total_cost=400_000,
            realized_pnl=0,
            cash_dividend=0.0,
        )

        by_ym = _net_investment_by_year_month(plan)
        assert set(by_ym) == {"2026-06"}
        assert _approx(by_ym["2026-06"], 50_000)


class TestPlanDeleteRecalculatesImmediateFollowingRecord:
    """plan_delete：刪除某月紀錄後，只有緊接的下一筆新制列淨投入跟著重算（SC-077）。"""

    @pytest.mark.scenario("SC-077")
    def test_sc077_delete_record_recalculates_only_the_record_after_it(
        self, service: CostBasisService
    ):
        holding = _holding(name="中華電", initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05", net_investment=50_000, total_cost=350_000, realized_income=0
            ),
            _record(
                year_month="2026-06", net_investment=50_000, total_cost=400_000, realized_income=0
            ),
            _record(
                year_month="2026-07", net_investment=20_000, total_cost=420_000, realized_income=0
            ),
        ]

        plan = service.plan_delete(holding=holding, records=records, year_month="2026-06")

        by_ym = _net_investment_by_year_month(plan)
        assert set(by_ym) == {"2026-07"}
        assert _approx(by_ym["2026-07"], 70_000)

    @pytest.mark.scenario("SC-077")
    def test_sc077_delete_first_record_causes_following_record_to_fall_back_to_initial_cost(
        self, service: CostBasisService
    ):
        """邊界自審：刪掉最早一筆後，下一筆的前期總成本改回退到項目初始成本。"""
        holding = _holding(name="中華電", initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05", net_investment=50_000, total_cost=350_000, realized_income=0
            ),
            _record(
                year_month="2026-06", net_investment=50_000, total_cost=400_000, realized_income=0
            ),
        ]

        plan = service.plan_delete(holding=holding, records=records, year_month="2026-05")

        by_ym = _net_investment_by_year_month(plan)
        assert set(by_ym) == {"2026-06"}
        assert _approx(by_ym["2026-06"], 100_000)

    @pytest.mark.scenario("SC-077")
    def test_sc077_delete_last_record_returns_empty_plan_when_nothing_follows(
        self, service: CostBasisService
    ):
        """邊界自審：刪掉的是最後一筆時，往後掃描沒有任何候選列，回傳空清單。"""
        holding = _holding(name="中華電", initial_cost=300_000)
        records = [
            _record(
                year_month="2026-05", net_investment=50_000, total_cost=350_000, realized_income=0
            ),
            _record(
                year_month="2026-06", net_investment=50_000, total_cost=400_000, realized_income=0
            ),
        ]

        plan = service.plan_delete(holding=holding, records=records, year_month="2026-06")

        assert plan == []


class TestPlanDeleteAcrossTransitionRecords:
    """plan_delete：連動重算跨越舊制列時，往後找到第一筆新制列才是真正受影響的（SC-078）。"""

    @pytest.mark.scenario("SC-078")
    def test_sc078_delete_earlier_legacy_record_skips_legacy_and_recalculates_next_new_style_record(
        self, service: CostBasisService
    ):
        holding = _holding(name="台達電", initial_cost=300_000)
        records = [
            _record(year_month="2026-01", net_investment=10_000),
            _record(year_month="2026-02", net_investment=15_000),
            _record(
                year_month="2026-03", net_investment=15_000, total_cost=340_000, realized_income=0
            ),
        ]

        plan = service.plan_delete(holding=holding, records=records, year_month="2026-01")

        by_ym = _net_investment_by_year_month(plan)
        assert set(by_ym) == {"2026-03"}
        assert _approx(by_ym["2026-03"], 25_000)


class TestPlanSaveDeletePlanValidation:
    """plan_save／plan_delete：限用於走總成本推算的分類，違反時拋出例外（同 SC-074 分類守門）。"""

    @pytest.mark.scenario("SC-074")
    def test_sc074_plan_save_rejects_holding_not_using_cost_basis(self, service: CostBasisService):
        holding = _holding(category=ASSET_CATEGORIES.DEMAND_DEPOSIT)

        with pytest.raises(DataValidationError):
            service.plan_save(
                holding=holding,
                records=[],
                year_month="2026-05",
                market_value=10_000,
                total_cost=10_000,
                realized_pnl=0,
                cash_dividend=0.0,
            )

    @pytest.mark.scenario("SC-074")
    def test_sc074_plan_delete_rejects_holding_not_using_cost_basis(
        self, service: CostBasisService
    ):
        holding = _holding(category=ASSET_CATEGORIES.DEMAND_DEPOSIT)

        with pytest.raises(DataValidationError):
            service.plan_delete(holding=holding, records=[], year_month="2026-05")


class TestTransferRecordsToWrite:
    """transfer_records_to_write：轉移成對紀錄中濾掉走總成本推算的股票/ETF 端（SC-079/080）。"""

    @pytest.mark.scenario("SC-079")
    def test_sc079_source_non_stock_dest_stock_only_source_written(self, service: CostBasisService):
        demand_deposit = _holding(
            holding_id=1, name="活存", category=ASSET_CATEGORIES.DEMAND_DEPOSIT
        )
        tsmc = _holding(holding_id=2, name="台積電", category=ASSET_CATEGORIES.TW_STOCK)
        source = _record(holding_id=1, year_month="2026-05", net_investment=-80_000)
        dest = _record(holding_id=2, year_month="2026-05", net_investment=80_000)

        result = service.transfer_records_to_write(
            pair=(source, dest), holdings=[demand_deposit, tsmc]
        )

        assert result == [source]

    @pytest.mark.scenario("SC-079")
    def test_sc079_source_stock_dest_non_stock_only_dest_written(self, service: CostBasisService):
        tsmc = _holding(holding_id=2, name="台積電", category=ASSET_CATEGORIES.TW_STOCK)
        demand_deposit = _holding(
            holding_id=1, name="活存", category=ASSET_CATEGORIES.DEMAND_DEPOSIT
        )
        source = _record(holding_id=2, year_month="2026-05", net_investment=-50_000)
        dest = _record(holding_id=1, year_month="2026-05", net_investment=50_000)

        result = service.transfer_records_to_write(
            pair=(source, dest), holdings=[tsmc, demand_deposit]
        )

        assert result == [dest]

    @pytest.mark.scenario("SC-079")
    def test_sc079_neither_end_stock_both_written_unchanged(self, service: CostBasisService):
        """邊界自審：兩端皆非股票/ETF 時不觸發任何過濾，成對紀錄原樣寫入。"""
        demand_deposit = _holding(
            holding_id=1, name="活存", category=ASSET_CATEGORIES.DEMAND_DEPOSIT
        )
        time_deposit = _holding(holding_id=4, name="定存", category=ASSET_CATEGORIES.TIME_DEPOSIT)
        source = _record(holding_id=1, year_month="2026-05", net_investment=-30_000)
        dest = _record(holding_id=4, year_month="2026-05", net_investment=30_000)

        result = service.transfer_records_to_write(
            pair=(source, dest), holdings=[demand_deposit, time_deposit]
        )

        assert result == [source, dest]

    @pytest.mark.scenario("SC-080")
    def test_sc080_both_ends_stock_neither_written(self, service: CostBasisService):
        tsmc = _holding(holding_id=2, name="台積電", category=ASSET_CATEGORIES.TW_STOCK)
        mediatek = _holding(holding_id=3, name="聯發科", category=ASSET_CATEGORIES.TW_STOCK)
        source = _record(holding_id=2, year_month="2026-05", net_investment=-60_000)
        dest = _record(holding_id=3, year_month="2026-05", net_investment=60_000)

        result = service.transfer_records_to_write(pair=(source, dest), holdings=[tsmc, mediatek])

        assert result == []


class TestRealizedPnlAndCashDividendSplit:
    """derive／plan_save：已實現損益與現金股利相加計入推算（SC-090）、現金股利非負（SC-091）。"""

    @pytest.mark.scenario("SC-090")
    def test_sc090_realized_pnl_and_cash_dividend_summed_into_formula(
        self, service: CostBasisService
    ):
        holding = _holding(name="日月光")
        records = [_record(year_month="2026-05", net_investment=0, total_cost=200_000)]

        result = service.derive(
            holding=holding,
            records=records,
            year_month="2026-06",
            total_cost=0,
            realized_pnl=100_000,
            cash_dividend=2_000,
        )

        assert _approx(result.net_investment, -302_000)

    @pytest.mark.scenario("SC-090")
    def test_sc090_plan_save_persists_split_and_sum(self, service: CostBasisService):
        holding = _holding(name="日月光")
        records = [_record(year_month="2026-05", net_investment=0, total_cost=200_000)]

        plan = service.plan_save(
            holding=holding,
            records=records,
            year_month="2026-06",
            market_value=0,
            total_cost=0,
            realized_pnl=100_000,
            cash_dividend=2_000,
        )

        saved = plan[0]
        assert _approx(saved.realized_income, 102_000)
        assert _approx(saved.cash_dividend, 2_000)
        assert _approx(saved.net_investment, -302_000)

    @pytest.mark.scenario("SC-074")
    def test_sc074_negative_realized_pnl_with_dividend_offsets_in_sum(
        self, service: CostBasisService
    ):
        holding = _holding(initial_cost=400_000)

        result = service.derive(
            holding=holding,
            records=[],
            year_month="2026-07",
            total_cost=380_000,
            realized_pnl=-5_000,
            cash_dividend=2_000,
        )

        # (380000 - 400000) - (-5000 + 2000) = -17000
        assert _approx(result.net_investment, -17_000)

    @pytest.mark.scenario("SC-091")
    def test_sc091_derive_rejects_negative_cash_dividend(self, service: CostBasisService):
        holding = _holding(name="日月光")

        with pytest.raises(DataValidationError, match="現金股利"):
            service.derive(
                holding=holding,
                records=[],
                year_month="2026-06",
                total_cost=0,
                realized_pnl=100_000,
                cash_dividend=-1_000,
            )

    @pytest.mark.scenario("SC-091")
    def test_sc091_plan_save_rejects_negative_cash_dividend(self, service: CostBasisService):
        holding = _holding(name="日月光")

        with pytest.raises(DataValidationError, match="現金股利"):
            service.plan_save(
                holding=holding,
                records=[],
                year_month="2026-06",
                market_value=0,
                total_cost=0,
                realized_pnl=100_000,
                cash_dividend=-1_000,
            )

    @pytest.mark.scenario("SC-091")
    def test_sc091_zero_cash_dividend_and_negative_realized_pnl_accepted(
        self, service: CostBasisService
    ):
        holding = _holding(initial_cost=100_000)

        result = service.derive(
            holding=holding,
            records=[],
            year_month="2026-06",
            total_cost=90_000,
            realized_pnl=-3_000,
            cash_dividend=0.0,
        )

        assert _approx(result.net_investment, -7_000)

    @pytest.mark.scenario("SC-078")
    def test_sc078_recalculation_uses_stored_realized_income_total(self, service: CostBasisService):
        """已存列的合計（已實現損益＋現金股利）直接用於連動重算，不需拆分。"""
        holding = _holding(name="台達電", initial_cost=300_000)
        records = [
            _record(year_month="2026-01", net_investment=10_000),
            _record(year_month="2026-02", net_investment=15_000),
            _record(
                year_month="2026-03",
                net_investment=0,
                total_cost=340_000,
                realized_income=7_000,
                cash_dividend=2_000,
            ),
        ]

        plan = service.plan_delete(holding=holding, records=records, year_month="2026-01")

        # (340000 - 315000) - 7000 = 18000
        assert _approx(_net_investment_by_year_month(plan)["2026-03"], 18_000)


class TestBuildCostBasisPrefill:
    """build_cost_basis_prefill：股票/ETF 錄入框帶入值，損益與現金股利分開（SC-088）。"""

    @pytest.mark.scenario("SC-088")
    def test_sc088_no_record_total_cost_and_market_value_blank_others_zero(
        self, service: CostBasisService
    ):
        prefill = service.build_cost_basis_prefill(records=[], year_month="2026-06")

        assert prefill.total_cost is None
        assert prefill.market_value is None
        assert prefill.realized_pnl == 0
        assert prefill.cash_dividend == 0

    @pytest.mark.scenario("SC-088")
    def test_sc088_existing_record_returns_split_values(self, service: CostBasisService):
        records = [
            _record(
                year_month="2026-05",
                market_value=650_000,
                total_cost=600_000,
                realized_income=11_500,
                cash_dividend=1_500,
            ),
        ]

        prefill = service.build_cost_basis_prefill(records=records, year_month="2026-05")

        assert prefill.total_cost == 600_000
        assert prefill.market_value == 650_000
        assert prefill.realized_pnl == 10_000
        assert prefill.cash_dividend == 1_500

    @pytest.mark.scenario("SC-088")
    def test_sc088_other_month_record_ignored(self, service: CostBasisService):
        records = [_record(year_month="2026-05", market_value=1, total_cost=1)]

        prefill = service.build_cost_basis_prefill(records=records, year_month="2026-06")

        assert prefill.total_cost is None
        assert prefill.market_value is None

    @pytest.mark.scenario("SC-088")
    def test_sc088_null_total_cost_and_market_value_prefill_blank(self, service: CostBasisService):
        records = [_record(year_month="2026-05", realized_income=500, cash_dividend=0)]

        prefill = service.build_cost_basis_prefill(records=records, year_month="2026-05")

        assert prefill.total_cost is None
        assert prefill.market_value is None
        assert prefill.realized_pnl == 500

    @pytest.mark.scenario("SC-088")
    def test_sc088_legacy_null_cash_dividend_all_counts_as_realized_pnl(
        self, service: CostBasisService
    ):
        records = [
            _record(
                year_month="2026-05",
                market_value=10,
                total_cost=10,
                realized_income=8_000,
                cash_dividend=None,
            ),
        ]

        prefill = service.build_cost_basis_prefill(records=records, year_month="2026-05")

        assert prefill.realized_pnl == 8_000
        assert prefill.cash_dividend == 0

    @pytest.mark.scenario("SC-088")
    def test_sc088_null_realized_income_prefills_zero(self, service: CostBasisService):
        records = [_record(year_month="2026-05", market_value=10, total_cost=10)]

        prefill = service.build_cost_basis_prefill(records=records, year_month="2026-05")

        assert prefill.realized_pnl == 0
        assert prefill.cash_dividend == 0
