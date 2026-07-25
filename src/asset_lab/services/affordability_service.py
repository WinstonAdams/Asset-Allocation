"""可負擔性試算引擎（本息均攤，純數學）。

本服務為純運算，不碰 I/O、不依賴 Streamlit、不含任何寫死的個人化數值——全部參數
由呼叫端顯式傳入（自備比率、驗算利率、貸款年限等亦不例外），可用虛構值窮舉公式與
往返一致性邊界。正算（由目標總價算月付）與反推（由月付上限算可負擔總價）共用同一套
本息均攤因子，僅套用方向不同（相乘 vs. 相除）。

寬限期不納入試算：本服務僅接受本金、利率、年限三個參數，一律以足額本息月付計算，
無寬限期概念的輸入介面。
"""

# ==== 原生（標準庫） ====

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
from asset_lab.models.results import AffordabilityResult

# 百分比與小數換算基準：利率、比率一律以百分比（0–100）傳入，換算時除以此值。
_PERCENT_BASE = 100.0

# 一年的月數，用於將貸款年限換算為總攤還期數。
_MONTHS_PER_YEAR = 12


class AffordabilityService:
    """本息均攤引擎（純數學，全部參數顯式傳入，無 baked-in 常數）。建構子無依賴。"""

    def __init__(self) -> None:
        """初始化可負擔性服務。本服務無外部依賴，僅做金融數學運算。"""

    def monthly_payment(
        self, *, principal: float, annual_rate_pct: float, years: int
    ) -> float:
        """計算等額本息月付。

        Args:
            principal: 貸款本金（TWD）。
            annual_rate_pct: 驗算利率，年化百分比（如 3 表示 3%）。
            years: 貸款年限（年）。

        Returns:
            每期（月）應繳金額（TWD）；annual_rate_pct 為 0 時退化為本金 ÷ 總期數。
        """
        return principal * self._amortization_factor(
            annual_rate_pct=annual_rate_pct, years=years
        )

    def affordable_total_price(
        self,
        *,
        monthly_income: float,
        payment_cap_ratio_pct: float,
        test_annual_rate_pct: float,
        loan_years: int,
        down_payment_ratio_pct: float,
    ) -> AffordabilityResult:
        """由月收與月付上限比率反推可負擔總價。

        月付上限 = 月收 × 月付上限比率；反推貸款上限（本息均攤因子的倒運算）；
        可負擔總價 = 貸款上限 ÷ (1 − 自備比率)，自備比率愈高，同一貸款上限
        合成的可負擔總價愈高。

        Args:
            monthly_income: 家庭稅後月收（TWD）。
            payment_cap_ratio_pct: 月付上限占月收的比率（百分比，如 40 表示 40%）。
            test_annual_rate_pct: 驗算利率，年化百分比。
            loan_years: 貸款年限（年）。
            down_payment_ratio_pct: 自備比率（百分比，如 20 表示 20%）。

        Returns:
            AffordabilityResult（direction='reverse'）：含月付上限、貸款上限、
            可負擔總價；forward 方向專屬欄位為 None。
        """
        monthly_payment_cap = monthly_income * payment_cap_ratio_pct / _PERCENT_BASE
        factor = self._amortization_factor(
            annual_rate_pct=test_annual_rate_pct, years=loan_years
        )
        loan_ceiling = monthly_payment_cap / factor
        affordable_total_price = loan_ceiling / (
            1 - down_payment_ratio_pct / _PERCENT_BASE
        )
        return AffordabilityResult(
            direction="reverse",
            affordable_total_price=affordable_total_price,
            loan_ceiling=loan_ceiling,
            monthly_payment_cap=monthly_payment_cap,
        )

    def payment_for_price(
        self,
        *,
        total_price: float,
        down_payment_ratio_pct: float,
        test_annual_rate_pct: float,
        loan_years: int,
        monthly_income: float,
    ) -> AffordabilityResult:
        """由目標總價正算本息均攤月付與月收占比。

        貸款金額 = 總價 × (1 − 自備比率)；自備款 = 總價 × 自備比率；月付為對貸款
        金額套用本息均攤公式的結果；月收占比 = 月付 ÷ 月收。月收為 0（尚未設定，
        見 SC-PENDING-001）時占比無法定義，回傳 None 而非拋出除以零例外。

        Args:
            total_price: 目標總價（TWD）。
            down_payment_ratio_pct: 自備比率（百分比，如 30 表示 30%）。
            test_annual_rate_pct: 驗算利率，年化百分比。
            loan_years: 貸款年限（年）。
            monthly_income: 家庭稅後月收（TWD）。

        Returns:
            AffordabilityResult（direction='forward'）：含貸款金額、自備款、月付、
            月收占比；reverse 方向專屬欄位為 None。
        """
        down_payment = total_price * down_payment_ratio_pct / _PERCENT_BASE
        loan_amount = total_price - down_payment
        monthly_payment = self.monthly_payment(
            principal=loan_amount, annual_rate_pct=test_annual_rate_pct, years=loan_years
        )
        income_share_pct = (
            monthly_payment / monthly_income * _PERCENT_BASE if monthly_income else None
        )
        return AffordabilityResult(
            direction="forward",
            monthly_payment=monthly_payment,
            income_share_pct=income_share_pct,
            loan_amount=loan_amount,
            down_payment=down_payment,
        )

    @staticmethod
    def _amortization_factor(*, annual_rate_pct: float, years: int) -> float:
        """本息均攤因子：月付 = 本金 × 此因子，反推時本金 = 月付 ÷ 此因子。

        因子 = 月利率 × (1+月利率)^期數 ÷ ((1+月利率)^期數 − 1)；年化利率為 0 時
        無法代入公式分母（會除以零），退化為 1 ÷ 總期數（即本金依期數均分）。
        """
        total_months = years * _MONTHS_PER_YEAR
        if annual_rate_pct == 0:
            return 1 / total_months
        monthly_rate = annual_rate_pct / _PERCENT_BASE / _MONTHS_PER_YEAR
        growth = (1 + monthly_rate) ** total_months
        return monthly_rate * growth / (growth - 1)
