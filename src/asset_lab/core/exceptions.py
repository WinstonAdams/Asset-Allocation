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


class SchemaError(AssetLabError):
    """資料庫結構建立或對齊失敗時拋出。"""
