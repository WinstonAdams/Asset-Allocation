"""計算輸出模型，與主檔模型分離。"""

# ==== 原生（標準庫） ====

# ==== 第三方套件 ====
from pydantic import BaseModel

# ==== 專案內部 ====
# 無


class ReturnResult(BaseModel):
    """單一維度的報酬率結果。

    dimension 為 'overall' / 'category' / 'holding'；dimension_key 為分類名或
    holding_id（overall 為 None）。mwr 不收斂時為 None 並以 mwr_status 標記。
    simple_return 在累積成本為 0 時為 None。annualized 未滿 12 月為 False。
    """

    dimension: str
    dimension_key: str | None = None
    twr: float | None = None
    mwr: float | None = None
    mwr_status: str
    simple_return: float | None = None
    pnl_amount: float | None = None
    annualized: bool


class CumulativeTwrPoint(BaseModel):
    """報酬率走勢圖單點：某有資料月的整體累積 TWR（僅資產）。

    cumulative_twr 為自區間起點累積至該月的時間加權報酬率（百分比小數）。
    """

    year_month: str
    cumulative_twr: float


class AllocationSnapshot(BaseModel):
    """某月份單一資產項目或分類的市值與佔比（僅資產）。

    weight 以百分比表示（0–100），與目標比重同單位。
    """

    year_month: str
    dimension_key: str
    market_value: float
    weight: float


class NetWorthPoint(BaseModel):
    """淨值趨勢單點。淨值＝總資產 − 總負債。"""

    year_month: str
    total_assets: float
    total_liabilities: float
    net_worth: float


class DriftRow(BaseModel):
    """目標偏離單列。權重一律百分比（0–100）。

    drift＝現況% − 目標%（百分點）；needs_rebalance 為 |drift| 超過門檻。
    """

    category: str
    current_weight: float
    target_weight: float
    drift: float
    needs_rebalance: bool


class AffordabilityResult(BaseModel):
    """可負擔性試算輸出（本息均攤引擎）。

    direction 為 'forward'（由目標總價正算月付）或 'reverse'（由月付上限反推可負擔
    總價）；未適用於該方向的欄位為 None（如 forward 結果的 affordable_total_price）。
    金額為 TWD，income_share_pct 為百分比（0–100）。
    """

    direction: str
    monthly_payment: float | None = None
    income_share_pct: float | None = None
    loan_amount: float | None = None
    down_payment: float | None = None
    affordable_total_price: float | None = None
    loan_ceiling: float | None = None
    monthly_payment_cap: float | None = None


class BucketProgress(BaseModel):
    """自備款 bucket 進度（BR-3/4/6）。

    target_amount＝目標總價×自備比率；gap 不為負值（bucket 超標時為 0）；
    progress_pct 以 target_amount 為分母，target_amount 為 0（目標未設定）時為 None，
    超標時呈現實際值、不封頂 100%。years_to_target 為 target_year − current_year，
    target_year 未設定（0）時為 None。reached_target_year 為 True 時
    （目標年已到或已過）required_annual_accumulation 為 None，避免除以零；
    target_year 未設定時兩者皆為中性姿態（reached_target_year=False、
    required_annual_accumulation=None）。
    """

    bucket_value: float
    target_amount: float
    gap: float
    progress_pct: float | None = None
    years_to_target: int | None = None
    reached_target_year: bool
    required_annual_accumulation: float | None = None


class BucketCompositionWarning(BaseModel):
    """bucket 組成序列風險提示（BR-8/D15）。只提示、不強制，不阻擋任何操作。

    has_non_cash 為 bucket 含非活存/定存分類資產（以現值判定，已出清的非現金項目
    不觸發）；intensified 為距目標購屋年 ≤5 年（含已到/已過）時的強化提示，
    目標年未設定時一律不強化。non_cash_value 為非活存/定存部分市值合計，供呈現。
    """

    has_non_cash: bool
    intensified: bool
    non_cash_value: float


class ProtocolStatus(BaseModel):
    """大跌行為協定等級判定結果（回撤 → 等級）。

    level_code 為 'L0'~'L3'；status 為 'ok'（依回撤深度判定）/
    'insufficient_data'（有資料但未達最低月數）/'no_data'（尚無任何有效節點）。
    drawdown 為目前自歷史高點回撤（≤0 小數，如 −0.22 表 −22%），資料不足時為
    None（不誤報大跌）。current_cumulative_twr 為最新有資料月的整體累積 TWR
    （小數），無任何節點時為 None；此欄位與協定等級判定無關，僅供關鍵指標呈現。
    data_month_count 為納入判定的累積 TWR 有效節點數。
    """

    level_code: str
    status: str
    drawdown: float | None = None
    current_cumulative_twr: float | None = None
    data_month_count: int
