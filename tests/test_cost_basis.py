"""CostBasisService：股票/ETF 依總成本與已實現收益推算當月淨投入（SC-074~078）。

CostBasisService 為純運算 Service（無 I/O、無 Streamlit），直接餵虛構的
HoldingModel/MonthlyRecordModel 驗證，不連任何 DB。所有金額皆為虛構值。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, COST_BASIS_INPUT, PREMIUM_INPUT
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
    return CostBasisService(
        cost_basis_categories=COST_BASIS_INPUT.CATEGORIES,
        premium_categories=PREMIUM_INPUT.CATEGORIES,
    )


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


# ==== 保險：累計已繳保費＋解約金＋本月領回 ====


def _insurance(*, holding_id: int = 1, initial_cost: float | None = 0.0) -> HoldingModel:
    """建立一個保險分類的資產項目主檔。"""
    return _holding(
        holding_id=holding_id,
        name="海外年金保單",
        category=ASSET_CATEGORIES.INSURANCE,
        initial_cost=initial_cost,
    )


def _premium_record(
    *,
    year_month: str,
    cumulative_premium: float,
    net_investment: float,
    surrender_value: float | None = 0.0,
    withdrawal: float = 0.0,
) -> MonthlyRecordModel:
    """建立一筆新制保險紀錄（total_cost＝累計保費、realized_income＝領回）。"""
    return _record(
        year_month=year_month,
        market_value=surrender_value,
        net_investment=net_investment,
        total_cost=cumulative_premium,
        realized_income=withdrawal,
    )


class TestDerivePremium:
    """derive_premium：淨投入＝(本月累計保費 − 前期累計保費) − 領回（SC-095、SC-096、SC-097）。"""

    @pytest.mark.scenario("SC-095")
    def test_sc095_previous_premium_from_prior_new_style_record(self, service: CostBasisService):
        records = [
            _premium_record(year_month="2026-04", cumulative_premium=600_000, net_investment=0)
        ]

        result = service.derive_premium(
            holding=_insurance(),
            records=records,
            year_month="2026-05",
            cumulative_premium=620_000,
            withdrawal=0,
        )

        assert _approx(result.previous_total_cost, 600_000)
        assert _approx(result.net_investment, 20_000)
        assert result.is_transition_estimate is False

    @pytest.mark.scenario("SC-095")
    def test_sc095_withdrawal_subtracted_from_net_investment(self, service: CostBasisService):
        records = [
            _premium_record(year_month="2026-05", cumulative_premium=620_000, net_investment=20_000)
        ]

        result = service.derive_premium(
            holding=_insurance(),
            records=records,
            year_month="2026-06",
            cumulative_premium=620_000,
            withdrawal=30_000,
        )

        assert _approx(result.net_investment, -30_000)

    @pytest.mark.scenario("SC-095")
    def test_sc095_first_record_uses_initial_cost_as_previous_premium(
        self, service: CostBasisService
    ):
        result = service.derive_premium(
            holding=_insurance(initial_cost=500_000),
            records=[],
            year_month="2026-05",
            cumulative_premium=520_000,
            withdrawal=0,
        )

        assert _approx(result.previous_total_cost, 500_000)
        assert _approx(result.net_investment, 20_000)

    @pytest.mark.scenario("SC-095")
    def test_sc095_surrender_month_net_investment_equals_negative_payout(
        self, service: CostBasisService
    ):
        records = [
            _premium_record(year_month="2026-05", cumulative_premium=620_000, net_investment=0)
        ]

        result = service.derive_premium(
            holding=_insurance(),
            records=records,
            year_month="2026-06",
            cumulative_premium=620_000,
            withdrawal=560_000,
        )

        assert _approx(result.net_investment, -560_000)

    @pytest.mark.scenario("SC-097")
    def test_sc097_previous_legacy_record_estimates_from_initial_cost_and_net_investment_sum(
        self, service: CostBasisService
    ):
        records = [
            _record(year_month="2026-02", net_investment=20_000),
            _record(year_month="2026-03", net_investment=20_000),
        ]

        result = service.derive_premium(
            holding=_insurance(initial_cost=500_000),
            records=records,
            year_month="2026-04",
            cumulative_premium=560_000,
            withdrawal=0,
        )

        assert _approx(result.previous_total_cost, 540_000)
        assert _approx(result.net_investment, 20_000)
        assert result.is_transition_estimate is True

    @pytest.mark.scenario("SC-097")
    def test_sc097_record_after_new_style_is_not_estimate(self, service: CostBasisService):
        records = [
            _record(year_month="2026-03", net_investment=20_000),
            _premium_record(
                year_month="2026-04", cumulative_premium=560_000, net_investment=20_000
            ),
        ]

        result = service.derive_premium(
            holding=_insurance(initial_cost=500_000),
            records=records,
            year_month="2026-05",
            cumulative_premium=580_000,
            withdrawal=0,
        )

        assert _approx(result.previous_total_cost, 560_000)
        assert result.is_transition_estimate is False

    @pytest.mark.scenario("SC-096")
    def test_sc096_derive_rejects_negative_withdrawal(self, service: CostBasisService):
        with pytest.raises(DataValidationError):
            service.derive_premium(
                holding=_insurance(),
                records=[],
                year_month="2026-06",
                cumulative_premium=620_000,
                withdrawal=-1_000,
            )

    @pytest.mark.scenario("SC-096")
    def test_sc096_zero_withdrawal_is_valid(self, service: CostBasisService):
        result = service.derive_premium(
            holding=_insurance(initial_cost=600_000),
            records=[],
            year_month="2026-06",
            cumulative_premium=620_000,
            withdrawal=0,
        )

        assert _approx(result.net_investment, 20_000)

    @pytest.mark.scenario("SC-096")
    def test_sc096_derive_rejects_non_premium_category(self, service: CostBasisService):
        with pytest.raises(DataValidationError):
            service.derive_premium(
                holding=_holding(category=ASSET_CATEGORIES.DEMAND_DEPOSIT),
                records=[],
                year_month="2026-06",
                cumulative_premium=1,
                withdrawal=0,
            )

    @pytest.mark.scenario("SC-096")
    def test_sc096_derive_rejects_stock_category(self, service: CostBasisService):
        with pytest.raises(DataValidationError):
            service.derive_premium(
                holding=_holding(category=ASSET_CATEGORIES.TW_STOCK),
                records=[],
                year_month="2026-06",
                cumulative_premium=1,
                withdrawal=0,
            )


class TestPlanSavePremium:
    """plan_save_premium：存檔列欄位對映與連動重算（SC-095、SC-096、SC-098）。"""

    @pytest.mark.scenario("SC-095")
    def test_sc095_plan_save_maps_fields_into_saved_row(self, service: CostBasisService):
        records = [
            _premium_record(year_month="2026-04", cumulative_premium=600_000, net_investment=0)
        ]

        plan = service.plan_save_premium(
            holding=_insurance(),
            records=records,
            year_month="2026-05",
            surrender_value=580_000,
            cumulative_premium=620_000,
            withdrawal=0,
        )

        saved = plan[0]
        assert saved.year_month == "2026-05"
        assert saved.market_value == 580_000
        assert saved.total_cost == 620_000
        assert saved.realized_income == 0
        assert saved.cash_dividend is None
        assert _approx(saved.net_investment, 20_000)
        assert len(plan) == 1

    @pytest.mark.scenario("SC-096")
    def test_sc096_plan_save_rejects_negative_withdrawal(self, service: CostBasisService):
        with pytest.raises(DataValidationError):
            service.plan_save_premium(
                holding=_insurance(),
                records=[],
                year_month="2026-06",
                surrender_value=585_000,
                cumulative_premium=620_000,
                withdrawal=-1_000,
            )

    @pytest.mark.scenario("SC-096")
    def test_sc096_plan_save_rejects_non_premium_category(self, service: CostBasisService):
        with pytest.raises(DataValidationError):
            service.plan_save_premium(
                holding=_holding(category=ASSET_CATEGORIES.TW_STOCK),
                records=[],
                year_month="2026-06",
                surrender_value=1,
                cumulative_premium=1,
                withdrawal=0,
            )

    @pytest.mark.scenario("SC-098")
    def test_sc098_edit_earlier_record_recalculates_only_following_changed_record(
        self, service: CostBasisService
    ):
        records = [
            _premium_record(
                year_month="2026-05", cumulative_premium=420_000, net_investment=20_000
            ),
            _premium_record(
                year_month="2026-06", cumulative_premium=440_000, net_investment=20_000
            ),
            _premium_record(
                year_month="2026-07", cumulative_premium=460_000, net_investment=20_000
            ),
        ]

        plan = service.plan_save_premium(
            holding=_insurance(initial_cost=400_000),
            records=records,
            year_month="2026-05",
            surrender_value=410_000,
            cumulative_premium=430_000,
            withdrawal=0,
        )

        by_ym = _net_investment_by_year_month(plan)
        assert set(by_ym) == {"2026-05", "2026-06"}
        assert _approx(by_ym["2026-05"], 30_000)
        assert _approx(by_ym["2026-06"], 10_000)

    @pytest.mark.scenario("SC-098")
    def test_sc098_legacy_record_after_edit_keeps_value_and_next_new_style_recalculated(
        self, service: CostBasisService
    ):
        # 2026-06 為舊制列（無累計保費），2026-07 為新制列，前期以過渡估算涵蓋被改的 2026-05
        records = [
            _premium_record(
                year_month="2026-05", cumulative_premium=420_000, net_investment=20_000
            ),
            _record(year_month="2026-06", net_investment=20_000),
            _premium_record(
                year_month="2026-07", cumulative_premium=460_000, net_investment=20_000
            ),
        ]

        plan = service.plan_save_premium(
            holding=_insurance(initial_cost=400_000),
            records=records,
            year_month="2026-05",
            surrender_value=410_000,
            cumulative_premium=430_000,
            withdrawal=0,
        )

        by_ym = _net_investment_by_year_month(plan)
        assert "2026-06" not in by_ym
        # 前期估算 = 400000 + 30000 + 20000 = 450000 → 460000 − 450000 = 10000
        assert _approx(by_ym["2026-07"], 10_000)


class TestPlanDeletePremium:
    """plan_delete：守門放寬為股票/ETF 或保險（SC-098）。"""

    @pytest.mark.scenario("SC-098")
    def test_sc098_delete_middle_record_recalculates_next_from_earlier(
        self, service: CostBasisService
    ):
        records = [
            _premium_record(
                year_month="2026-05", cumulative_premium=420_000, net_investment=20_000
            ),
            _premium_record(
                year_month="2026-06", cumulative_premium=440_000, net_investment=20_000
            ),
            _premium_record(
                year_month="2026-07", cumulative_premium=460_000, net_investment=20_000
            ),
        ]

        plan = service.plan_delete(
            holding=_insurance(initial_cost=400_000), records=records, year_month="2026-06"
        )

        by_ym = _net_investment_by_year_month(plan)
        assert set(by_ym) == {"2026-07"}
        assert _approx(by_ym["2026-07"], 40_000)

    @pytest.mark.scenario("SC-098")
    def test_sc098_plan_delete_still_rejects_non_stock_non_premium(self, service: CostBasisService):
        with pytest.raises(DataValidationError):
            service.plan_delete(
                holding=_holding(category=ASSET_CATEGORIES.DEMAND_DEPOSIT),
                records=[],
                year_month="2026-06",
            )


class TestBuildPremiumPrefill:
    """build_premium_prefill：保險錄入框帶入值（SC-099）。"""

    @pytest.mark.scenario("SC-099")
    def test_sc099_existing_record_returns_stored_values(self, service: CostBasisService):
        records = [
            _premium_record(
                year_month="2026-05",
                cumulative_premium=620_000,
                net_investment=20_000,
                surrender_value=580_000,
                withdrawal=0,
            )
        ]

        prefill = service.build_premium_prefill(records=records, year_month="2026-05")

        assert prefill.cumulative_premium == 620_000
        assert prefill.surrender_value == 580_000
        assert prefill.withdrawal == 0

    @pytest.mark.scenario("SC-099")
    def test_sc099_no_record_blank_required_fields_zero_withdrawal(self, service: CostBasisService):
        records = [
            _premium_record(year_month="2026-05", cumulative_premium=620_000, net_investment=0)
        ]

        prefill = service.build_premium_prefill(records=records, year_month="2026-06")

        assert prefill.cumulative_premium is None
        assert prefill.surrender_value is None
        assert prefill.withdrawal == 0.0

    @pytest.mark.scenario("SC-099")
    def test_sc099_record_with_blank_values_prefills_blank_not_zero(
        self, service: CostBasisService
    ):
        records = [
            _record(year_month="2026-05", market_value=None, total_cost=None, realized_income=None)
        ]

        prefill = service.build_premium_prefill(records=records, year_month="2026-05")

        assert prefill.cumulative_premium is None
        assert prefill.surrender_value is None
        assert prefill.withdrawal == 0.0

    @pytest.mark.scenario("SC-099")
    def test_sc099_nonzero_withdrawal_prefilled(self, service: CostBasisService):
        records = [
            _premium_record(
                year_month="2026-06",
                cumulative_premium=620_000,
                net_investment=-30_000,
                surrender_value=585_000,
                withdrawal=30_000,
            )
        ]

        prefill = service.build_premium_prefill(records=records, year_month="2026-06")

        assert prefill.withdrawal == 30_000
