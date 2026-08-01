"""持有項目主檔模型。"""

# ==== 原生（標準庫） ====

# ==== 第三方套件 ====
from pydantic import BaseModel

# ==== 專案內部 ====
# 無


class HoldingModel(BaseModel):
    """持有項目主檔。

    kind 為 'asset' 或 'liability'；負債的 category 與 initial_* 皆為 None。
    holding_id 為穩定身分，改名不影響歷史連乘；新增時為 None，由 DB 產生後回填。
    purpose 為純附加用途標記（一般/購屋，預設一般，對應 HOLDING_PURPOSE.GENERAL；
    Model 不 import constants，見 03-data-config.md，值與 constants.py 手動保持一致），
    只供買房功能讀取，既有分類/報酬/配置計算完全不讀此欄（D14）。
    """

    holding_id: int | None = None
    name: str
    kind: str
    category: str | None = None
    initial_market_value: float | None = None
    initial_cost: float | None = None
    purpose: str = "general"
