"""買房參數的合併與存前驗證（純運算）。

本檔目前只涵蓋買房參數持久化這條垂直切片（已存值 + 中性預設合併、落庫前驗證）；
bucket 進度、觸發檢核、總覽摘要等買房評估邏輯由後續擴充補上同一個 HouseService。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
from asset_lab.core.constants import HOUSE_PARAM_DEFAULTS, HOUSE_PARAM_KEY
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.house import HouseParamModel, HouseParams

# 比率型參數（自備比率、月付上限比率）的合法域為開區間：恰為 0（等同未設定/無自備）
# 或 100（等同無貸款）皆非有效的政策比率，須嚴格介於兩端點之間。
_RATIO_MIN = 0.0
_RATIO_MAX = 100.0


class HouseService:
    """買房評估（純運算，無依賴）。"""

    def __init__(self) -> None:
        """初始化買房服務。本服務無外部依賴，僅做純運算。"""

    def effective_params(self, *, stored: list[HouseParamModel]) -> HouseParams:
        """以已存值覆蓋中性預設、缺鍵補中性預設，回傳型別化的有效買房參數。

        使用者從未存過任何參數（stored 為空）時全數採中性/方法論預設；只存了
        部分鍵時，已存鍵用已存值、缺的鍵各自補對應預設，不因其他鍵缺失而失敗。
        target_year 與 loan_years 在此還原為 int（表中統一以 REAL 儲存）。

        Args:
            stored: 已保存的買房參數列（可能不完整，0～9 筆，任意順序）。

        Returns:
            合併中性預設後的有效買房參數。
        """
        overrides = {param.param_key: param.param_value for param in stored}
        return HouseParams(
            target_total_price=overrides.get(
                HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE, HOUSE_PARAM_DEFAULTS.TARGET_TOTAL_PRICE
            ),
            target_year=int(
                overrides.get(HOUSE_PARAM_KEY.TARGET_YEAR, HOUSE_PARAM_DEFAULTS.TARGET_YEAR)
            ),
            monthly_after_tax_income=overrides.get(
                HOUSE_PARAM_KEY.MONTHLY_AFTER_TAX_INCOME,
                HOUSE_PARAM_DEFAULTS.MONTHLY_AFTER_TAX_INCOME,
            ),
            income_threshold=overrides.get(
                HOUSE_PARAM_KEY.INCOME_THRESHOLD, HOUSE_PARAM_DEFAULTS.INCOME_THRESHOLD
            ),
            cash_floor=overrides.get(
                HOUSE_PARAM_KEY.CASH_FLOOR, HOUSE_PARAM_DEFAULTS.CASH_FLOOR
            ),
            down_payment_ratio=overrides.get(
                HOUSE_PARAM_KEY.DOWN_PAYMENT_RATIO, HOUSE_PARAM_DEFAULTS.DOWN_PAYMENT_RATIO
            ),
            payment_cap_ratio=overrides.get(
                HOUSE_PARAM_KEY.PAYMENT_CAP_RATIO, HOUSE_PARAM_DEFAULTS.PAYMENT_CAP_RATIO
            ),
            test_annual_rate=overrides.get(
                HOUSE_PARAM_KEY.TEST_ANNUAL_RATE, HOUSE_PARAM_DEFAULTS.TEST_ANNUAL_RATE
            ),
            loan_years=int(
                overrides.get(HOUSE_PARAM_KEY.LOAN_YEARS, HOUSE_PARAM_DEFAULTS.LOAN_YEARS)
            ),
        )

    def validate_params(self, *, params: HouseParams) -> None:
        """存前驗證：比率須嚴格介於 0～100、驗算利率非負、貸款年限為正整數、
        金額與年份非負（0 為合法值，代表尚未設定）。

        呼叫端（設定頁）應在寫入前對整組候選參數呼叫本方法，驗證失敗時不落 DB、
        不變更既有參數（逐項檢查、一次回報所有違規項）。

        Args:
            params: 待存入的候選買房參數（使用者輸入合併而成的完整一組九個參數）。

        Raises:
            DataValidationError: 任一參數逾越合法域。
        """
        errors: list[str] = []

        for label, value in (
            ("自備比率", params.down_payment_ratio),
            ("月付上限比率", params.payment_cap_ratio),
        ):
            if not (_RATIO_MIN < value < _RATIO_MAX):
                errors.append(f"{label}須介於 0～100 之間（不含兩端點），收到 {value}")

        if params.test_annual_rate < 0:
            errors.append(f"驗算利率不可為負，收到 {params.test_annual_rate}")

        if params.loan_years <= 0:
            errors.append(f"貸款年限須為正整數，收到 {params.loan_years}")

        for label, value in (
            ("目標總價", params.target_total_price),
            ("家庭稅後月收", params.monthly_after_tax_income),
            ("收入門檻", params.income_threshold),
            ("現金地板", params.cash_floor),
        ):
            if value < 0:
                errors.append(f"{label}不可為負，收到 {value}")

        if params.target_year < 0:
            errors.append(f"目標購屋年份不可為負，收到 {params.target_year}")

        if errors:
            raise DataValidationError("；".join(errors))
