"""買房參數與主觀觸發勾選的持久化模型。"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
from pydantic import BaseModel

# ==== 專案內部 ====
# 無


class HouseParamModel(BaseModel):
    """單一買房參數持久化列（比照 ProtocolThresholdModel）。

    param_key 為 HOUSE_PARAM_KEY 值域；param_value 統一以 REAL 儲存（含比率、
    金額、年份），型別化還原（如年份轉 int）由 HouseService.effective_params 處理。
    """

    param_key: str
    param_value: float


class SubjectiveTriggerModel(BaseModel):
    """單一主觀觸發條件的勾選狀態持久化列。

    trigger_key 為 HOUSE_TRIGGER.SUBJECTIVE 值域（定錨/認知）。
    """

    trigger_key: str
    checked: bool


class HouseParams(BaseModel):
    """合併中性預設後的有效買房參數（比照 ProtocolThresholds）。

    比率欄位（down_payment_ratio/payment_cap_ratio/test_annual_rate）為百分比
    （0–100）；金額欄位（target_total_price/monthly_after_tax_income/
    income_threshold/cash_floor）為 TWD；target_year 為西元年、loan_years 為
    貸款年限，皆已還原為 int。
    """

    target_total_price: float
    target_year: int
    monthly_after_tax_income: float
    income_threshold: float
    cash_floor: float
    down_payment_ratio: float
    payment_cap_ratio: float
    test_annual_rate: float
    loan_years: int
