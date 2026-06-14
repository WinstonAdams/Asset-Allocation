"""分類目標配置模型。"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
from pydantic import BaseModel

# ==== 專案內部 ====
# 無


class TargetAllocationModel(BaseModel):
    """分類目標配置。

    target_weight 以百分比表示（0–100），各分類目標總和應為 100%。
    """

    category: str
    target_weight: float
