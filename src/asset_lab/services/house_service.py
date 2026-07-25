"""買房參數的合併驗證、自備款 bucket 口徑與進度評估（純運算）。

本檔涵蓋買房參數持久化（已存值 + 中性預設合併、落庫前驗證）與自備款 bucket
（購屋標記項目市值合計、目標進度、組成序列風險提示）兩條垂直切片；觸發條件
檢核、總覽摘要等買房評估邏輯由後續擴充補上同一個 HouseService。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    HOLDING_PURPOSE,
    HOUSE_PARAM_DEFAULTS,
    HOUSE_PARAM_KEY,
)
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParamModel, HouseParams
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import BucketCompositionWarning, BucketProgress

# 比率型參數（自備比率、月付上限比率）的合法域為開區間：恰為 0（等同未設定/無自備）
# 或 100（等同無貸款）皆非有效的政策比率，須嚴格介於兩端點之間。
_RATIO_MIN = 0.0
_RATIO_MAX = 100.0

# bucket 組成警示的「現金」分類：僅活存/定存視為無序列風險；其餘分類（股票等）
# 因價格會波動，於接近購屋年時贖回可能被迫低點變現（序列風險）。
_CASH_CATEGORIES = (ASSET_CATEGORIES.DEMAND_DEPOSIT, ASSET_CATEGORIES.TIME_DEPOSIT)

# 距目標購屋年僅剩少數年時，非現金資產下跌後已無足夠時間等待回本，
# 序列風險提示須強化為醒目等級。
_INTENSIFY_YEARS_THRESHOLD = 5


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

    def bucket_value(
        self,
        *,
        month_records: list[MonthlyRecordModel],
        holdings: list[HoldingModel],
    ) -> float:
        """自備款 bucket 值：購屋標記項目的最新月度市值合計（BR-3）。

        僅計 purpose=house 的項目；一般項目一律不計入。無任何購屋標記項目時為 0。

        Args:
            month_records: 全部項目的月度紀錄（可橫跨多月，供判定「是否曾有紀錄」）。
            holdings: 項目主檔清單，用於篩選購屋標記項目。

        Returns:
            購屋標記項目現值合計（TWD）。
        """
        house_holdings = [h for h in holdings if h.purpose == HOLDING_PURPOSE.HOUSE]
        values = self._current_house_values(
            house_holdings=house_holdings, month_records=month_records
        )
        return sum(values.values())

    def bucket_progress(
        self,
        *,
        bucket_value: float,
        params: HouseParams,
        current_year: int,
    ) -> BucketProgress:
        """自備款 bucket 進度：目標金額、缺口、進度百分比與每年需累積速率（BR-2/BR-6）。

        進度百分比不封頂（bucket 超標時呈現實際值）；目標購屋年已到或已過時不算
        每年需累積速率（避免除以零），改由 reached_target_year 標示；目標年未設定
        （0）時剩餘年數未知，速率與「已到目標年」皆不呈現。

        Args:
            bucket_value: 自備款 bucket 現值（TWD），由 bucket_value() 算得。
            params: 有效買房參數，提供目標總價、自備比率與目標購屋年份。
            current_year: 當前年份（西元年），由呼叫端顯式傳入。

        Returns:
            bucket 進度結果模型。
        """
        target_amount = params.target_total_price * params.down_payment_ratio / 100.0
        gap = max(target_amount - bucket_value, 0.0)
        progress_pct = None if target_amount == 0 else bucket_value / target_amount * 100.0

        if params.target_year == 0:
            years_to_target = None
            reached_target_year = False
            required_annual_accumulation = None
        else:
            years_to_target = params.target_year - current_year
            reached_target_year = years_to_target <= 0
            required_annual_accumulation = (
                None if reached_target_year else gap / years_to_target
            )

        return BucketProgress(
            bucket_value=bucket_value,
            target_amount=target_amount,
            gap=gap,
            progress_pct=progress_pct,
            years_to_target=years_to_target,
            reached_target_year=reached_target_year,
            required_annual_accumulation=required_annual_accumulation,
        )

    def bucket_composition_warning(
        self,
        *,
        house_holdings: list[HoldingModel],
        month_records: list[MonthlyRecordModel],
        years_to_target: int | None,
    ) -> BucketCompositionWarning:
        """bucket 組成序列風險提示：含非活存/定存資產時提示，距目標年≤5年強化（BR-8/D15）。

        只提示、不強制（不阻擋任何操作、不自動再平衡）。目標年未設定（None）時
        剩餘年數未知，一律不強化；已到/已過目標年（≤0）視為比剩 5 年更緊迫，同樣強化。

        Args:
            house_holdings: 購屋標記項目主檔清單（呼叫端已篩選 purpose=house）。
            month_records: 全部項目的月度紀錄（可橫跨多月，供判定現值口徑）。
            years_to_target: 距目標購屋年剩餘年數，未設定目標年時為 None。

        Returns:
            bucket 組成警示結果模型。
        """
        values = self._current_house_values(
            house_holdings=house_holdings, month_records=month_records
        )
        non_cash_value = sum(
            values.get(holding.holding_id, 0.0)
            for holding in house_holdings
            if holding.category not in _CASH_CATEGORIES
        )
        return BucketCompositionWarning(
            has_non_cash=non_cash_value > 0,
            intensified=years_to_target is not None
            and years_to_target <= _INTENSIFY_YEARS_THRESHOLD,
            non_cash_value=non_cash_value,
        )

    def _current_house_values(
        self,
        *,
        house_holdings: list[HoldingModel],
        month_records: list[MonthlyRecordModel],
    ) -> dict[int, float]:
        """算各購屋標記項目在最新月快照的現值，供 bucket 合計與組成細分共用同一口徑。

        項目完全無任何月度紀錄時以初始市值補（尚未有市場波動的起始部位）；項目在
        最新月有紀錄時採該筆市值（留空視為未更新、不貢獻，即 0，與 AllocationService
        同口徑）；項目曾有紀錄但最新月缺列（已不再持有）時亦為 0——初始市值僅用於
        「從無任何月度紀錄」的情形，不回退已出清項目的初始市值。

        Args:
            house_holdings: 購屋標記項目主檔清單。
            month_records: 全部項目的月度紀錄（可橫跨多月）。

        Returns:
            holding_id → 現值（TWD）的字典。
        """
        records_by_holding: dict[int, list[MonthlyRecordModel]] = {}
        for record in month_records:
            records_by_holding.setdefault(record.holding_id, []).append(record)

        latest_year_month = self._latest_year_month(month_records)

        values: dict[int, float] = {}
        for holding in house_holdings:
            records = records_by_holding.get(holding.holding_id, [])
            if not records:
                values[holding.holding_id] = holding.initial_market_value or 0.0
                continue
            latest_record = next(
                (record for record in records if record.year_month == latest_year_month),
                None,
            )
            values[holding.holding_id] = (
                (latest_record.market_value or 0.0) if latest_record is not None else 0.0
            )
        return values

    @staticmethod
    def _latest_year_month(records: list[MonthlyRecordModel]) -> str | None:
        """從月度紀錄取出最新（字典序即時序，'YYYY-MM' 格式）年月；無紀錄時為 None。"""
        year_months = {record.year_month for record in records}
        return max(year_months) if year_months else None
