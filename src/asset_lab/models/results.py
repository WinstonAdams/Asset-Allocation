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
