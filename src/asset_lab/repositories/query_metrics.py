"""查詢量測：每執行緒累計資料庫往返、快取命中與重連旗標（不依賴 Streamlit）。

Streamlit 每個 session 的腳本跑在自己的執行緒，計數以 threading.local 隔離，多個 session
的數字不會混進同一行 log；另保留一個加鎖的程序累計往返數，讓測試能在別的執行緒跑腳本
（AppTest）時仍以前後差值斷言。
"""

# ==== 原生（標準庫） ====
import threading
from dataclasses import dataclass

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
# 無


@dataclass(frozen=True)
class QueryMetricsSnapshot:
    """一次執行的量測值。"""

    db_roundtrips: int
    cache_hits: int
    reconnected: bool


class _ThreadCounters(threading.local):
    """各執行緒獨立的累計值；threading.local 子類的 __init__ 會在每個新執行緒各跑一次。"""

    def __init__(self) -> None:
        self.db_roundtrips = 0
        self.cache_hits = 0
        self.reconnected = False


class QueryMetrics:
    """每執行緒累計的查詢量測，加上程序累計往返數（測試用）。"""

    def __init__(self) -> None:
        self._local = _ThreadCounters()
        self._lock = threading.Lock()
        self._total_roundtrips = 0

    def add_roundtrip(self) -> None:
        """記一次資料庫往返（本執行緒與程序累計各加一）。"""
        self._local.db_roundtrips += 1
        with self._lock:
            self._total_roundtrips += 1

    def add_cache_hit(self) -> None:
        """記一次快取命中。"""
        self._local.cache_hits += 1

    def mark_reconnected(self) -> None:
        """標記本執行緒這次執行發生過重連。"""
        self._local.reconnected = True

    def take(self) -> QueryMetricsSnapshot:
        """讀取本執行緒累計值並歸零。"""
        local = self._local
        snapshot = QueryMetricsSnapshot(
            db_roundtrips=local.db_roundtrips,
            cache_hits=local.cache_hits,
            reconnected=local.reconnected,
        )
        local.db_roundtrips = 0
        local.cache_hits = 0
        local.reconnected = False
        return snapshot

    def total_roundtrips(self) -> int:
        """程序啟動以來的總往返數（不歸零）；測試以前後差值斷言。"""
        with self._lock:
            return self._total_roundtrips
