"""CachingConnection／CachingCursor：read-through 快取、commit 成功才清、寫入中繞過快取。

以 :memory: libsql 連線為內層，經計數層（記錄真正往返）再包快取層，與正式組裝一致。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import libsql
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND
from asset_lab.models.holding import HoldingModel
from asset_lab.repositories.connection_layers import CachingConnection, CountingConnection
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.query_metrics import QueryMetrics
from asset_lab.repositories.read_cache import ReadCache
from asset_lab.repositories.schema_repository import SchemaRepository

_SELECT = "SELECT v FROM t WHERE k = ?"


class _Rig:
    """內層 libsql → 計數層 → 快取層的測試裝配。"""

    def __init__(self, inner=None) -> None:
        self.raw = inner if inner is not None else libsql.connect(":memory:")
        self.metrics = QueryMetrics()
        self.cache = ReadCache(ttl_seconds=300)
        counted = CountingConnection(inner=self.raw, metrics=self.metrics)
        self.conn = CachingConnection(inner=counted, cache=self.cache, metrics=self.metrics)
        cursor = self.raw.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS t (k INTEGER PRIMARY KEY, v INTEGER)")
        cursor.execute("INSERT INTO t (k, v) VALUES (1, 100)")
        self.raw.commit()

    def read(self, key: int = 1) -> list[tuple]:
        cursor = self.conn.cursor()
        cursor.execute(_SELECT, (key,))
        return cursor.fetchall()

    def roundtrips_during(self, action) -> int:
        before = self.metrics.total_roundtrips()
        action()
        return self.metrics.total_roundtrips() - before


@pytest.fixture
def rig() -> _Rig:
    return _Rig()


@pytest.mark.scenario("SC-112")
def test_sc112_second_identical_select_does_not_hit_database(rig: _Rig) -> None:
    first = rig.read()

    trips = rig.roundtrips_during(lambda: rig.read())

    assert trips == 0
    assert rig.read() == first == [(100,)]


@pytest.mark.scenario("SC-112")
def test_sc112_cache_hit_is_recorded_in_metrics(rig: _Rig) -> None:
    rig.read()
    rig.metrics.take()

    rig.read()

    assert rig.metrics.take().cache_hits == 1


@pytest.mark.scenario("SC-112")
def test_sc112_different_parameters_are_different_queries(rig: _Rig) -> None:
    rig.read(1)

    trips = rig.roundtrips_during(lambda: rig.read(2))

    assert trips == 1


@pytest.mark.scenario("SC-112")
def test_sc112_empty_result_is_cached_too(rig: _Rig) -> None:
    assert rig.read(99) == []

    trips = rig.roundtrips_during(lambda: rig.read(99))

    assert trips == 0


@pytest.mark.scenario("SC-112")
def test_sc112_select_detection_ignores_leading_space_and_case(rig: _Rig) -> None:
    def read_lower() -> list[tuple]:
        cursor = rig.conn.cursor()
        cursor.execute("  \n select v FROM t WHERE k = ?", (1,))
        return cursor.fetchall()

    read_lower()

    assert rig.roundtrips_during(read_lower) == 0


@pytest.mark.scenario("SC-112")
def test_sc112_fetchone_reads_from_buffer_then_none(rig: _Rig) -> None:
    rig.read()
    cursor = rig.conn.cursor()

    cursor.execute(_SELECT, (1,))

    assert cursor.fetchone() == (100,)
    assert cursor.fetchone() is None


@pytest.mark.scenario("SC-112")
def test_sc112_execute_returns_cursor_for_chaining(rig: _Rig) -> None:
    cursor = rig.conn.cursor()

    assert cursor.execute(_SELECT, (1,)) is cursor
    assert cursor.fetchall() == [(100,)]


@pytest.mark.scenario("SC-112")
def test_sc112_empty_parameter_tuple_is_cacheable(rig: _Rig) -> None:
    def read_without_params() -> list[tuple]:
        cursor = rig.conn.cursor()
        cursor.execute("SELECT v FROM t WHERE k = 1", ())
        return cursor.fetchall()

    read_without_params()

    assert rig.roundtrips_during(read_without_params) == 0


@pytest.mark.scenario("SC-112")
def test_sc112_non_sequence_parameters_pass_through_uncached() -> None:
    calls: list[object] = []

    class _FakeCursor:
        def execute(self, sql, parameters=()):
            calls.append(parameters)

        def fetchall(self):
            return [(1,)]

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def commit(self) -> None: ...

        def rollback(self) -> None: ...

    cache = ReadCache(ttl_seconds=300)
    conn = CachingConnection(inner=_FakeConn(), cache=cache, metrics=QueryMetrics())
    named = {"k": 1}

    for _ in range(2):
        cursor = conn.cursor()
        cursor.execute("SELECT v FROM t WHERE k = :k", named)
        assert cursor.fetchall() == [(1,)]

    assert calls == [named, named]  # 兩次都打內層、不快取


@pytest.mark.scenario("SC-113")
def test_sc113_successful_commit_clears_cache_and_next_read_is_fresh(rig: _Rig) -> None:
    assert rig.read() == [(100,)]
    writer = rig.conn.cursor()

    writer.execute("UPDATE t SET v = ? WHERE k = ?", (120, 1))
    rig.conn.commit()

    assert rig.read() == [(120,)]


@pytest.mark.scenario("SC-113")
def test_sc113_commit_clears_all_cached_queries(rig: _Rig) -> None:
    rig.read(1)
    rig.read(2)
    writer = rig.conn.cursor()
    writer.execute("UPDATE t SET v = ? WHERE k = ?", (120, 1))
    rig.conn.commit()

    assert rig.roundtrips_during(lambda: rig.read(2)) == 1


@pytest.mark.scenario("SC-113")
def test_sc113_delete_then_commit_makes_row_disappear(rig: _Rig) -> None:
    rig.read()
    writer = rig.conn.cursor()
    writer.execute("DELETE FROM t WHERE k = ?", (1,))
    rig.conn.commit()

    assert rig.read() == []


@pytest.mark.scenario("SC-113")
def test_sc113_write_cursor_exposes_lastrowid_and_forwards_fetch(rig: _Rig) -> None:
    writer = rig.conn.cursor()

    writer.execute("INSERT INTO t (k, v) VALUES (?, ?)", (5, 50))

    assert writer.lastrowid == 5
    rig.conn.commit()


@pytest.mark.scenario("SC-113")
def test_sc113_batch_write_clears_only_after_final_commit(rig: _Rig) -> None:
    rig.read()
    writer = rig.conn.cursor()
    writer.execute("UPDATE t SET v = 1 WHERE k = 1")
    writer.execute("INSERT INTO t (k, v) VALUES (2, 2)")

    # commit 前，快取內既有項目尚未被清（但有未 commit 的寫入時，讀取會繞過快取）
    assert rig.cache.get((_SELECT, (1,))) == [(100,)]

    rig.conn.commit()

    assert rig.cache.get((_SELECT, (1,))) is None


@pytest.mark.scenario("SC-114")
def test_sc114_commit_failure_keeps_cache(rig: _Rig) -> None:
    rig.read()

    class _FailCommit:
        def __init__(self, inner) -> None:
            self._inner = inner

        def cursor(self):
            return self._inner.cursor()

        def commit(self) -> None:
            raise ValueError("commit boom")

        def rollback(self) -> None:
            self._inner.rollback()

    conn = CachingConnection(
        inner=_FailCommit(CountingConnection(inner=rig.raw, metrics=rig.metrics)),
        cache=rig.cache,
        metrics=rig.metrics,
    )
    conn.cursor().execute("UPDATE t SET v = 999 WHERE k = 1")

    with pytest.raises(ValueError, match="commit boom"):
        conn.commit()

    assert rig.cache.get((_SELECT, (1,))) == [(100,)]


@pytest.mark.scenario("SC-114")
def test_sc114_rollback_keeps_existing_entries(rig: _Rig) -> None:
    rig.read()
    writer = rig.conn.cursor()
    writer.execute("UPDATE t SET v = 999 WHERE k = 1")

    rig.conn.rollback()

    assert rig.cache.get((_SELECT, (1,))) == [(100,)]
    assert rig.read() == [(100,)]


@pytest.mark.scenario("SC-114")
def test_sc114_after_rollback_cached_data_is_still_usable_without_roundtrip(rig: _Rig) -> None:
    rig.read()
    writer = rig.conn.cursor()
    writer.execute("UPDATE t SET v = 999 WHERE k = 1")
    rig.conn.rollback()

    assert rig.roundtrips_during(lambda: rig.read()) == 0


@pytest.mark.scenario("SC-114")
def test_sc114_read_during_pending_write_bypasses_cache_and_is_not_stored(rig: _Rig) -> None:
    writer = rig.conn.cursor()
    writer.execute("UPDATE t SET v = 999 WHERE k = 1")  # 尚未 commit

    seen = rig.read()

    assert seen == [(999,)]  # 直接查資料庫
    assert rig.cache.get((_SELECT, (1,))) is None  # 未確認的資料不得留在快取


@pytest.mark.scenario("SC-114")
def test_sc114_pending_write_that_fails_in_execute_still_bypasses_cache(rig: _Rig) -> None:
    rig.read()
    writer = rig.conn.cursor()
    with pytest.raises(ValueError):
        writer.execute("INSERT INTO t (k, v) VALUES (1, 1)")  # 主鍵重複

    # 旗標在 execute 前就成立；失敗後沒有 rollback 前讀取仍繞過快取
    assert rig.roundtrips_during(lambda: rig.read()) == 1

    rig.conn.rollback()

    assert rig.roundtrips_during(lambda: rig.read()) == 0


@pytest.mark.scenario("SC-114")
def test_sc114_write_flag_cleared_after_commit_so_caching_resumes(rig: _Rig) -> None:
    writer = rig.conn.cursor()
    writer.execute("UPDATE t SET v = 7 WHERE k = 1")
    rig.conn.commit()

    rig.read()

    assert rig.roundtrips_during(lambda: rig.read()) == 0


@pytest.mark.scenario("SC-114")
def test_sc114_query_in_flight_when_commit_happens_is_not_written_back(rig: _Rig) -> None:
    # 未命中查詢發出後、結果寫回前，別的執行緒 commit：世代已變，結果不寫回
    class _CommitDuringFetch:
        """內層 cursor 在 fetchall 時模擬『同時發生』一次 commit 清除。"""

        def __init__(self, inner_cursor, on_fetch) -> None:
            self._inner = inner_cursor
            self._on_fetch = on_fetch

        def execute(self, sql, parameters=()):
            self._inner.execute(sql, parameters)
            return self

        def fetchall(self):
            rows = self._inner.fetchall()
            self._on_fetch()
            return rows

        def fetchone(self):
            return self._inner.fetchone()

        @property
        def lastrowid(self):
            return self._inner.lastrowid

    class _Wrapper:
        def __init__(self, inner, on_fetch) -> None:
            self._inner = inner
            self._on_fetch = on_fetch

        def cursor(self):
            return _CommitDuringFetch(self._inner.cursor(), self._on_fetch)

        def commit(self) -> None:
            self._inner.commit()

        def rollback(self) -> None:
            self._inner.rollback()

    conn = CachingConnection(
        inner=_Wrapper(
            CountingConnection(inner=rig.raw, metrics=rig.metrics), on_fetch=rig.cache.clear
        ),
        cache=rig.cache,
        metrics=rig.metrics,
    )
    cursor = conn.cursor()

    cursor.execute(_SELECT, (1,))

    assert cursor.fetchall() == [(100,)]
    assert rig.cache.get((_SELECT, (1,))) is None


@pytest.mark.scenario("SC-112")
def test_sc112_unsupported_interfaces_raise_attribute_error(rig: _Rig) -> None:
    cursor = rig.conn.cursor()

    with pytest.raises(AttributeError):
        rig.conn.execute("SELECT 1")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        cursor.fetchmany(1)  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        cursor.executemany("SELECT 1", [])  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        cursor.description  # type: ignore[attr-defined]  # noqa: B018


@pytest.mark.scenario("SC-112")
def test_sc112_cache_hit_does_not_create_inner_cursor() -> None:
    raw = libsql.connect(":memory:")
    created = {"count": 0}

    class _CountingFactory:
        def __init__(self, inner) -> None:
            self._inner = inner

        def cursor(self):
            created["count"] += 1
            return self._inner.cursor()

        def commit(self) -> None:
            self._inner.commit()

        def rollback(self) -> None:
            self._inner.rollback()

    metrics = QueryMetrics()
    cache = ReadCache(ttl_seconds=300)
    conn = CachingConnection(inner=_CountingFactory(raw), cache=cache, metrics=metrics)
    cache.put(("SELECT 1", ()), [(1,)], generation=cache.generation())

    cursor = conn.cursor()
    cursor.execute("SELECT 1", ())

    assert cursor.fetchall() == [(1,)]
    assert created["count"] == 0


@pytest.mark.scenario("SC-119")
def test_sc119_caller_mutating_fetched_rows_does_not_affect_cache(rig: _Rig) -> None:
    rig.read()
    cursor = rig.conn.cursor()
    cursor.execute(_SELECT, (1,))
    rows = cursor.fetchall()
    rows.append((777,))

    assert rig.read() == [(100,)]


@pytest.mark.scenario("SC-119")
def test_sc119_cached_repository_read_equals_uncached_and_mutation_is_isolated() -> None:
    raw = libsql.connect(":memory:")
    SchemaRepository(conn=raw).ensure_schema()
    metrics = QueryMetrics()
    cache = ReadCache(ttl_seconds=300)
    cached = CachingConnection(
        inner=CountingConnection(inner=raw, metrics=metrics), cache=cache, metrics=metrics
    )
    cached_repo = HoldingRepository(conn=cached)
    plain_repo = HoldingRepository(conn=raw)
    cached_repo.add_holding(
        holding=HoldingModel(
            name="範例定存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            initial_market_value=1000.0,
            initial_cost=1000.0,
        )
    )

    first = cached_repo.list_holdings()
    first[0].name = "被呼叫端改掉"
    second = cached_repo.list_holdings()

    assert second == plain_repo.list_holdings()
    assert second[0].name == "範例定存"
