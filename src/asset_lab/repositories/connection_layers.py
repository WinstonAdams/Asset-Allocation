"""連線包裝層：計數層記錄實際打到資料庫的往返，快取層在其上做 SELECT read-through。

Repository 拿到的連線是這一層包住的 libsql 連線，Repository 本身的程式碼不變。計數以
「往返」近似：每次 execute、commit、rollback 算一次（失敗也算），cursor() 與 fetch* 不算。

只提供目前 Repository 用到的介面（連線：cursor／commit／rollback；cursor：execute／
fetchall／fetchone／lastrowid），刻意不用 __getattr__ 轉發：以後有人用到 description、
fetchmany、executemany 等介面時會直接拋 AttributeError，而不是默默拿到沒被計數的結果。

快取層（CachingConnection）疊在計數層之上，所以計數的是「真的打到資料庫」的往返，快取
命中不算。語意：SELECT 以 (sql, 參數) 為鍵 read-through；commit 成功才清快取；有未
commit 的寫入時讀取繞過快取，且結果不寫回；rollback 只推進世代、不清既有項目。
"""

# ==== 原生（標準庫） ====
from collections.abc import Sequence
from typing import Protocol

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.repositories.query_metrics import QueryMetrics
from asset_lab.repositories.read_cache import ReadCache

# 語句開頭為此字樣（去前導空白、不分大小寫）才視為可快取的讀取。
_SELECT_PREFIX = "SELECT"


class DbCursor(Protocol):
    """Repository 使用的 cursor 介面。"""

    def execute(self, sql: str, parameters: Sequence[object] = ...) -> object: ...
    def fetchall(self) -> list[tuple]: ...
    def fetchone(self) -> tuple | None: ...
    @property
    def lastrowid(self) -> int | None: ...


class DbConnection(Protocol):
    """Repository 使用的連線介面。"""

    def cursor(self) -> DbCursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class CountingConnection:
    """計數層：每次 execute／commit／rollback 記一次往返後轉給內層（失敗也算）。"""

    def __init__(self, *, inner: DbConnection, metrics: QueryMetrics) -> None:
        self._inner = inner
        self._metrics = metrics

    def cursor(self) -> "CountingCursor":
        """建立包住內層 cursor 的計數 cursor（建立本身不算往返）。"""
        return CountingCursor(inner=self._inner.cursor(), metrics=self._metrics)

    def commit(self) -> None:
        """先計數再 commit，commit 失敗也算一次往返。"""
        self._metrics.add_roundtrip()
        self._inner.commit()

    def rollback(self) -> None:
        """先計數再 rollback，rollback 失敗也算一次往返。"""
        self._metrics.add_roundtrip()
        self._inner.rollback()


class CountingCursor:
    """計數 cursor：execute 記一次往返；fetch* 與 lastrowid 直接透傳不計數。"""

    def __init__(self, *, inner: DbCursor, metrics: QueryMetrics) -> None:
        self._inner = inner
        self._metrics = metrics

    def execute(self, sql: str, parameters: Sequence[object] = ()) -> "CountingCursor":
        """先計數再執行；回傳自己，與 libsql cursor 的鏈式呼叫行為一致。"""
        self._metrics.add_roundtrip()
        self._inner.execute(sql, parameters)
        return self

    def fetchall(self) -> list[tuple]:
        """取回全部 rows（不計數）。"""
        return self._inner.fetchall()

    def fetchone(self) -> tuple | None:
        """取回一筆 row（不計數）。"""
        return self._inner.fetchone()

    @property
    def lastrowid(self) -> int | None:
        """最近一次 INSERT 的 rowid。"""
        return self._inner.lastrowid


class CachingConnection:
    """快取層：SELECT read-through；commit 成功才清；有未 commit 的寫入時繞過快取。

    只提供 cursor／commit／rollback，不轉發其他屬性；用到未提供的介面會拋 AttributeError。
    """

    def __init__(self, *, inner: DbConnection, cache: ReadCache, metrics: QueryMetrics) -> None:
        self._inner = inner
        self._cache = cache
        self._metrics = metrics
        # 有寫入語句已送出但尚未 commit／rollback 成功；在內層執行之前就設為真，
        # 才擋得住別的執行緒在這段期間讀到尚未確認的資料並存進快取。
        self._pending_write = False

    @property
    def pending_write(self) -> bool:
        """目前是否有尚未確認的寫入。"""
        return self._pending_write

    def mark_pending_write(self) -> None:
        """標記有寫入進行中（cursor 在執行非 SELECT 語句之前呼叫）。"""
        self._pending_write = True

    @property
    def cache(self) -> ReadCache:
        """快取實例（cursor 讀寫用）。"""
        return self._cache

    @property
    def metrics(self) -> QueryMetrics:
        """量測累計器（cursor 記命中用）。"""
        return self._metrics

    def new_inner_cursor(self) -> DbCursor:
        """建立內層 cursor（只在真的需要打資料庫時才呼叫）。"""
        return self._inner.cursor()

    def cursor(self) -> "CachingCursor":
        """建立快取 cursor；此時不建立內層 cursor。"""
        return CachingCursor(owner=self)

    def commit(self) -> None:
        """內層 commit 成功才清快取並清除寫入旗標；失敗原樣往上拋、不清。"""
        self._inner.commit()
        self._cache.clear()
        self._pending_write = False

    def rollback(self) -> None:
        """不論成敗都推進世代（既有項目保留）；成功才清除寫入旗標，失敗原樣往上拋。"""
        try:
            self._inner.rollback()
        finally:
            self._cache.fence()
        self._pending_write = False


class CachingCursor:
    """快取 cursor：SELECT 走快取（命中則緩衝 rows），其他語句標記寫入後透傳。"""

    def __init__(self, *, owner: CachingConnection) -> None:
        self._owner = owner
        self._inner: DbCursor | None = None
        self._buffer: list[tuple] | None = None

    def execute(self, sql: str, parameters: Sequence[object] = ()) -> "CachingCursor":
        """SELECT：命中直接緩衝；未命中查資料庫並在安全時寫回。其他語句：先標記寫入再透傳。"""
        self._buffer = None
        if not sql.lstrip().upper().startswith(_SELECT_PREFIX):
            self._owner.mark_pending_write()
            self._ensure_inner().execute(sql, parameters)
            return self

        cacheable = isinstance(parameters, tuple | list)
        key = (sql, tuple(parameters)) if cacheable else None
        cache = self._owner.cache
        if key is not None and not self._owner.pending_write:
            hit = cache.get(key)
            if hit is not None:
                self._owner.metrics.add_cache_hit()
                self._buffer = list(hit)
                return self

        generation = cache.generation()
        inner = self._ensure_inner()
        inner.execute(sql, parameters)
        rows = inner.fetchall()
        # 寫入進行中時結果可能含未確認的資料，不寫回；世代已變時 put 會自行拒絕
        if key is not None and not self._owner.pending_write:
            cache.put(key, rows, generation=generation)
        self._buffer = list(rows)
        return self

    def fetchall(self) -> list[tuple]:
        """取回全部 rows（SELECT 從緩衝區讀；其他語句透傳）。"""
        if self._buffer is None:
            return self._ensure_inner().fetchall()
        rows, self._buffer = self._buffer, []
        return rows

    def fetchone(self) -> tuple | None:
        """取回一筆 row（SELECT 從緩衝區讀；其他語句透傳）。"""
        if self._buffer is None:
            return self._ensure_inner().fetchone()
        return self._buffer.pop(0) if self._buffer else None

    @property
    def lastrowid(self) -> int | None:
        """最近一次 INSERT 的 rowid；從未打過資料庫的 cursor 為 None。"""
        return None if self._inner is None else self._inner.lastrowid

    def _ensure_inner(self) -> DbCursor:
        if self._inner is None:
            self._inner = self._owner.new_inner_cursor()
        return self._inner
