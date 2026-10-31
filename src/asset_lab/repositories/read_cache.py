"""程序級的查詢結果快取：整批過期、世代計數、執行緒安全；不依賴 Streamlit。

所有 session 的腳本執行緒共用同一份快取（資料是否有效跟連線與使用者無關），因此：
- 內部以 Lock 保護；
- 「清除」與「rollback」都推進世代，未命中查詢先取世代、結果回來才帶著世代寫回，
  世代已變就丟棄，擋住「查詢進行中被 commit 清除、舊結果又被寫回」的競態；
- 過期是整批的（從清除後第一筆寫入起算），同一次執行看到的是一致的快照。
"""

# ==== 原生（標準庫） ====
import threading
import time
from collections.abc import Callable

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
# 無

CacheKey = tuple[str, tuple[object, ...]]


class ReadCache:
    """依 (sql, 參數) 存取查詢結果 rows 的快取。"""

    def __init__(self, *, ttl_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        """建立空快取。

        Args:
            ttl_seconds: 整批過期秒數，從清除後第一筆寫入起算。
            clock: 單調時鐘；測試可注入假時鐘。
        """
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[CacheKey, list[tuple]] = {}
        self._generation = 0
        self._started_at: float | None = None

    def get(self, key: CacheKey) -> list[tuple] | None:
        """查詢快取。

        Args:
            key: (sql, 參數) 組成的鍵。

        Returns:
            命中回傳快取的 rows（呼叫端不得修改）；未命中回傳 None。空清單是合法的命中值。
        """
        with self._lock:
            return self._items.get(key)

    def generation(self) -> int:
        """取得目前世代；未命中查詢前先取得，寫回時帶入。

        Returns:
            目前的世代數。
        """
        with self._lock:
            return self._generation

    def put(self, key: CacheKey, rows: list[tuple], *, generation: int) -> bool:
        """寫入查詢結果；清除後第一筆寫入同時記下 TTL 起算時間。

        Args:
            key: (sql, 參數) 組成的鍵。
            rows: 查詢結果 rows。
            generation: 查詢前取得的世代；已被推進則丟棄。

        Returns:
            世代仍相同而寫入成功回 True，否則 False。
        """
        with self._lock:
            if generation != self._generation:
                return False
            if self._started_at is None:
                self._started_at = self._clock()
            self._items[key] = list(rows)
            return True

    def clear(self) -> None:
        """清空全部項目、推進世代、重設 TTL 起算時間。"""
        with self._lock:
            self._items.clear()
            self._generation += 1
            self._started_at = None

    def fence(self) -> None:
        """只推進世代、保留既有項目（rollback 時用，讓進行中的未命中查詢不寫回）。"""
        with self._lock:
            self._generation += 1

    def expire_if_stale(self) -> bool:
        """距 TTL 起算時間已達 ttl_seconds 就整批清除；只在每次執行的入口呼叫。

        Returns:
            有清除回 True，未到期回 False。
        """
        with self._lock:
            started_at = self._started_at
            if started_at is None or self._clock() - started_at < self._ttl_seconds:
                return False
        self.clear()
        return True
