# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.services.affordability_service import AffordabilityService


def _approx(value: float | None, expected: float, abs_: float = 1e-6) -> bool:
    """以浮點容差比較試算結果數值。"""
    return value is not None and value == pytest.approx(expected, abs=abs_)


class TestPaymentForPriceForward:
    """payment_for_price：由目標總價正算本息均攤月付與月收占比（SC-052）。"""

    @pytest.mark.scenario("SC-052")
    def test_sc052_forward_calculates_loan_down_payment_and_monthly_payment(self):
        result = AffordabilityService().payment_for_price(
            total_price=10_000_000,
            down_payment_ratio_pct=30,
            test_annual_rate_pct=3,
            loan_years=20,
            monthly_income=100_000,
        )
        assert result.direction == "forward"
        assert _approx(result.loan_amount, 7_000_000)
        assert _approx(result.down_payment, 3_000_000)
        # 月利率 0.25%、240 期的等額本息封閉解，約 38,822 元
        assert _approx(result.monthly_payment, 38_821.83, abs_=0.01)
        # 月付 ÷ 家庭稅後月收 ≈ 38.8%
        assert _approx(result.income_share_pct, 38.8218, abs_=0.001)
        # reverse 方向專屬欄位於 forward 結果不適用，須為 None
        assert result.affordable_total_price is None
        assert result.loan_ceiling is None
        assert result.monthly_payment_cap is None

    @pytest.mark.scenario("SC-052")
    def test_sc052_zero_rate_degenerates_to_principal_divided_by_months(self):
        # 驗算利率 0% 時退化為本金均分：貸款 7,200,000 元、年限 30 年 → 月付 20,000 元
        service = AffordabilityService()
        monthly_payment = service.monthly_payment(
            principal=7_200_000, annual_rate_pct=0, years=30
        )
        assert _approx(monthly_payment, 20_000)


class TestAffordableTotalPriceReverse:
    """affordable_total_price：由月收與月付上限反推可負擔總價（SC-053）。"""

    @pytest.mark.scenario("SC-053")
    def test_sc053_reverse_calculates_payment_cap_loan_ceiling_and_affordable_price(self):
        result = AffordabilityService().affordable_total_price(
            monthly_income=100_000,
            payment_cap_ratio_pct=40,
            test_annual_rate_pct=0,
            loan_years=20,
            down_payment_ratio_pct=20,
        )
        assert result.direction == "reverse"
        assert _approx(result.monthly_payment_cap, 40_000)
        assert _approx(result.loan_ceiling, 9_600_000)
        assert _approx(result.affordable_total_price, 12_000_000)
        # forward 方向專屬欄位於 reverse 結果不適用，須為 None
        assert result.monthly_payment is None
        assert result.income_share_pct is None
        assert result.loan_amount is None
        assert result.down_payment is None

    @pytest.mark.scenario("SC-053")
    def test_sc053_round_trip_consistency_with_nonzero_rate(self):
        # 以任一組非零利率參數反推可負擔總價後，用同一組參數正算，
        # 月付應等於月付上限（浮點容差內）
        service = AffordabilityService()
        reverse_result = service.affordable_total_price(
            monthly_income=100_000,
            payment_cap_ratio_pct=40,
            test_annual_rate_pct=3,
            loan_years=20,
            down_payment_ratio_pct=20,
        )
        forward_result = service.payment_for_price(
            total_price=reverse_result.affordable_total_price,
            down_payment_ratio_pct=20,
            test_annual_rate_pct=3,
            loan_years=20,
            monthly_income=100_000,
        )
        assert _approx(forward_result.monthly_payment, reverse_result.monthly_payment_cap)

    @pytest.mark.scenario("SC-053")
    def test_sc053_higher_down_payment_ratio_yields_higher_affordable_price(self):
        # 自備比率愈高，同一貸款上限合成的可負擔總價愈高：20% → ÷0.8；50% → ÷0.5
        service = AffordabilityService()
        low_ratio_result = service.affordable_total_price(
            monthly_income=100_000,
            payment_cap_ratio_pct=40,
            test_annual_rate_pct=3,
            loan_years=20,
            down_payment_ratio_pct=20,
        )
        high_ratio_result = service.affordable_total_price(
            monthly_income=100_000,
            payment_cap_ratio_pct=40,
            test_annual_rate_pct=3,
            loan_years=20,
            down_payment_ratio_pct=50,
        )
        # 同一貸款上限（利率/年限/月付上限皆同），僅自備比率不同
        assert _approx(low_ratio_result.loan_ceiling, high_ratio_result.loan_ceiling)
        assert _approx(
            low_ratio_result.affordable_total_price,
            low_ratio_result.loan_ceiling / 0.8,
        )
        assert _approx(
            high_ratio_result.affordable_total_price,
            high_ratio_result.loan_ceiling / 0.5,
        )
        assert high_ratio_result.affordable_total_price > low_ratio_result.affordable_total_price


class TestSamePurePureFunctionConsistency:
    """引擎為零依賴純運算：同一輸入重複呼叫應得到一致結果（無隱藏狀態）。"""

    @pytest.mark.scenario("SC-052")
    def test_sc052_same_input_yields_same_result_across_calls(self):
        service = AffordabilityService()
        first = service.payment_for_price(
            total_price=10_000_000,
            down_payment_ratio_pct=30,
            test_annual_rate_pct=3,
            loan_years=20,
            monthly_income=100_000,
        )
        second = service.payment_for_price(
            total_price=10_000_000,
            down_payment_ratio_pct=30,
            test_annual_rate_pct=3,
            loan_years=20,
            monthly_income=100_000,
        )
        assert first.monthly_payment == second.monthly_payment


class TestForwardZeroIncome:
    """正算時家庭稅後月收為 0（尚未設定）之月付占比呈現（SC-072）。"""

    @pytest.mark.scenario("SC-072")
    def test_sc072_zero_income_forward_returns_none_income_share(self):
        result = AffordabilityService().payment_for_price(
            total_price=10_000_000,
            down_payment_ratio_pct=30,
            test_annual_rate_pct=3,
            loan_years=20,
            monthly_income=0,
        )
        # 月收未設定（0）：占比無法定義，回傳 None 而非拋出除以零例外
        assert result.income_share_pct is None
        # 其餘不涉及月收的欄位仍正常計算
        assert _approx(result.loan_amount, 7_000_000)
        assert _approx(result.down_payment, 3_000_000)
        assert _approx(result.monthly_payment, 38_821.83, abs_=0.01)
