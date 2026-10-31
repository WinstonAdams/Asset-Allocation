"""QueryMetrics 與計數層 CountingConnection／CountingCursor 的單元測試（SC-130）。

計數層放在連線最底層，數字代表「真的打到資料庫的次數」：每次 execute／commit／rollback
算一次往返（失敗也算），cursor() 與 fetch* 不算。
"""

# ==== 原生（標準庫） ====
import threading

# ==== 第三方套件 ====
import libsql
import pytest

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.repositories.connection_layers import CountingConnection
from asset_lab.repositories.query_metrics import QueryMetrics, QueryMetricsSnapshot
from asset_lab.repositories.read_cache import ReadCache


class _ExplodingConnection:
    """execute／commit／rollback 一律失敗的內層連線，用來驗證失敗也計數。"""

    def cursor(self) -> "_ExplodingConnection":
        return self

    def execute(self, sql: str, parameters: tuple = ()) -> None:
        raise ValueError("boom")

    def commit(self) -> None:
        raise ValueError("boom")

    def rollback(self) -> None:
        raise ValueError("boom")


@pytest.mark.scenario("SC-130")
def test_sc130_take_returns_accumulated_values_and_resets() -> None:
    metrics = QueryMetrics()
    metrics.add_roundtrip()
    metrics.add_roundtrip()
    metrics.add_cache_hit()
    metrics.mark_reconnected()

    first = metrics.take()
    second = metrics.take()

    assert first == QueryMetricsSnapshot(db_roundtrips=2, cache_hits=1, reconnected=True)
    assert second == QueryMetricsSnapshot(db_roundtrips=0, cache_hits=0, reconnected=False)


@pytest.mark.scenario("SC-130")
def test_sc130_total_roundtrips_is_not_reset_by_take() -> None:
    metrics = QueryMetrics()
    metrics.add_roundtrip()
    metrics.take()
    metrics.add_roundtrip()

    assert metrics.total_roundtrips() == 2


@pytest.mark.scenario("SC-130")
def test_sc130_counts_are_isolated_per_thread() -> None:
    # 多個 session 各跑在自己的執行緒：別的執行緒的往返不能混進本執行緒的一行 log
    metrics = QueryMetrics()
    metrics.add_roundtrip()

    def other_thread() -> None:
        metrics.add_roundtrip()
        metrics.add_roundtrip()
        metrics.add_cache_hit()
        metrics.mark_reconnected()

    worker = threading.Thread(target=other_thread)
    worker.start()
    worker.join()

    mine = metrics.take()
    assert mine == QueryMetricsSnapshot(db_roundtrips=1, cache_hits=0, reconnected=False)
    # 程序累計包含所有執行緒
    assert metrics.total_roundtrips() == 3


@pytest.mark.scenario("SC-130")
def test_sc130_counting_connection_counts_execute_commit_rollback() -> None:
    metrics = QueryMetrics()
    inner = libsql.connect(":memory:")
    conn = CountingConnection(inner=inner, metrics=metrics)

    cursor = conn.cursor()
    cursor.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    cursor.execute("INSERT INTO t (v) VALUES (?)", ("a",))
    conn.commit()
    cursor.execute("SELECT v FROM t WHERE v = ?", ("a",))
    rows = cursor.fetchall()
    conn.rollback()

    assert rows == [("a",)]
    # execute x3、commit x1、rollback x1；cursor() 與 fetchall 不算
    assert metrics.take().db_roundtrips == 5


@pytest.mark.scenario("SC-130")
def test_sc130_counting_cursor_passes_through_fetchone_and_lastrowid() -> None:
    metrics = QueryMetrics()
    conn = CountingConnection(inner=libsql.connect(":memory:"), metrics=metrics)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    cursor.execute("INSERT INTO t (v) VALUES (?)", ("a",))
    new_id = cursor.lastrowid
    cursor.execute("SELECT v FROM t WHERE id = ?", (new_id,))

    assert new_id == 1
    assert cursor.fetchone() == ("a",)


@pytest.mark.scenario("SC-130")
def test_sc130_counting_cursor_execute_returns_self_for_chaining() -> None:
    conn = CountingConnection(inner=libsql.connect(":memory:"), metrics=QueryMetrics())
    cursor = conn.cursor()

    assert cursor.execute("SELECT 1") is cursor


@pytest.mark.scenario("SC-130")
def test_sc130_failed_operations_are_still_counted_and_error_propagates() -> None:
    metrics = QueryMetrics()
    conn = CountingConnection(inner=_ExplodingConnection(), metrics=metrics)

    with pytest.raises(ValueError):
        conn.cursor().execute("SELECT 1")
    with pytest.raises(ValueError):
        conn.commit()
    with pytest.raises(ValueError):
        conn.rollback()

    assert metrics.take().db_roundtrips == 3


@pytest.mark.scenario("SC-130")
def test_sc130_counting_layer_does_not_forward_unknown_attributes() -> None:
    # 只提供 Repository 用到的介面；用到未提供的介面要明確失敗，不默默轉發
    conn = CountingConnection(inner=libsql.connect(":memory:"), metrics=QueryMetrics())

    with pytest.raises(AttributeError):
        conn.executemany  # noqa: B018
    with pytest.raises(AttributeError):
        conn.cursor().fetchmany  # noqa: B018


@pytest.mark.scenario("SC-130")
def test_sc130_build_container_routes_repository_io_through_counting_layer() -> None:
    metrics = QueryMetrics()
    inner = libsql.connect(":memory:")

    container = bootstrap.build_container(
        conn=inner,
        read_cache=ReadCache(ttl_seconds=300),
        query_metrics=metrics,
    )
    container.schema_repo.ensure_schema()

    assert isinstance(container.holding_repo._conn._inner, CountingConnection)
    assert container.holding_repo._conn is container.record_repo._conn
    assert metrics.take().db_roundtrips > 0
