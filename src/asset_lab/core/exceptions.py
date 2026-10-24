"""業務例外定義。下層拋出、由 Page 層統一捕捉並反饋使用者。"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
# 無


class AssetLabError(Exception):
    """本工具所有業務例外的共同基底，方便上層一次捕捉。"""


class DataValidationError(AssetLabError):
    """資料格式或內容不符規格時拋出（如年月格式錯誤、CSV 匯入唯一鍵重複）。"""


class ProtocolDocError(AssetLabError):
    """行為協定文件（docs/PROTOCOL.md）讀取失敗時拋出（缺失、無法讀取等），交 Page 層反饋。"""


class SchemaError(AssetLabError):
    """資料庫結構建立或對齊失敗時拋出。"""


class PersistenceError(AssetLabError):
    """資料庫寫入失敗且已復原（資料未變更）時拋出，預設訊息可直接顯示給使用者。

    訊息刻意不內插原始錯誤（避免 SQL、表名等細節出現在畫面）；原始錯誤由 `__cause__`
    保留，交由上層記錄到 log。
    """

    DEFAULT_MESSAGE = "存檔失敗，資料未變更，請重試"

    def __init__(self, message: str = DEFAULT_MESSAGE) -> None:
        super().__init__(message)
