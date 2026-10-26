"""連線存活探測 I/O：以最便宜的一次往返確認連線可用。"""

# ==== 原生（標準庫） ====
# 無
# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.repositories.connection_layers import DbConnection

# 最便宜的存活探測：不碰任何資料表，只確認連線能往返。
_PING_SQL = "SELECT 1"


class ConnectionHealthRepository:
    """連線存活探測。必須注入不經快取的連線（計數層），否則探測永遠命中快取。"""

    def __init__(self, *, conn: DbConnection) -> None:
        self._conn = conn

    def ping(self) -> None:
        """執行 SELECT 1 並取回結果；失敗原樣往上拋，交由重連邏輯判斷。"""
        cursor = self._conn.cursor()
        cursor.execute(_PING_SQL)
        cursor.fetchall()
