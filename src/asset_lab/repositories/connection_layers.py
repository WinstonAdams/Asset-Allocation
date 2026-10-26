"""連線包裝層：計數層把每次實際打到資料庫的操作記進 QueryMetrics。

Repository 拿到的連線是這一層包住的 libsql 連線，Repository 本身的程式碼不變。計數以
「往返」近似：每次 execute、commit、rollback 算一次（失敗也算），cursor() 與 fetch* 不算。

只提供目前 Repository 用到的介面（連線：cursor／commit／rollback；cursor：execute／
fetchall／fetchone／lastrowid），刻意不用 __getattr__ 轉發：以後有人用到 description、
fetchmany、executemany 等介面時會直接拋 AttributeError，而不是默默拿到沒被計數的結果。
"""

# ==== 原生（標準庫） ====
from collections.abc import Sequence
from typing import Protocol

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.repositories.query_metrics import QueryMetrics


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
