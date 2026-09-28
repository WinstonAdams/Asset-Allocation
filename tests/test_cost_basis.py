"""CostBasisService：股票/ETF 依總成本與已實現收益推算當月淨投入（SC-074/075/076）。

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
) -> MonthlyRecordModel:
    """建立一筆月度紀錄（供 derive 系列測試組出前期紀錄序列）。"""
    return MonthlyRecordModel(
        holding_id=holding_id,
        year_month=year_month,
        market_value=market_value,
        net_investment=net_investment,
        total_cost=total_cost,
        realized_income=realized_income,
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
            realized_income=0,
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
            realized_income=0,
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
            realized_income=15_000,
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
            realized_income=-5_000,
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
            realized_income=0,
        )

        assert _approx(result.previous_total_cost, 0.0)
        assert _approx(result.net_investment, 10_000)

    @pytest.mark.scenario("SC-074")
    def test_sc074_derive_rejects_holding_not_using_cost_basis(
        self, service: CostBasisService
    ):
        holding = _holding(category=ASSET_CATEGORIES.DEMAND_DEPOSIT)

        with pytest.raises(DataValidationError):
            service.derive(
                holding=holding,
                records=[],
                year_month="2026-05",
                total_cost=10_000,
                realized_income=0,
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
            realized_income=0,
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
            realized_income=50_000,
        )

        assert _approx(result.previous_total_cost, 350_000)
        assert _approx(result.net_investment, -400_000)
