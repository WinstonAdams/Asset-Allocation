"""大跌行為協定的回撤門檻設定模型。"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
from pydantic import BaseModel

# ==== 專案內部 ====
# 無


class ProtocolThresholdModel(BaseModel):
    """單一等級的回撤門檻設定持久化列。

    level 為 'L1'/'L2'/'L3'；drawdown_threshold 為正回撤幅度百分比
    （如 10.0 表示自歷史高點回撤達 10% 時進入該級）。
    """

    level: str
    drawdown_threshold: float


class ProtocolThresholds(BaseModel):
    """合併預設值後的有效回撤門檻，供等級判定使用。

    三級皆為正回撤幅度百分比，且應滿足 l1 < l2 < l3（深度嚴格遞增）。
    """

    l1: float
    l2: float
    l3: float
