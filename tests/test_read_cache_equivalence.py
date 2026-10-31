"""有無快取的計算結果一致（SC-119）與同一次重跑內重複查詢去重（SC-118）。

以同一份種子資料，分別經「只計數」與「計數＋快取」兩種組裝的 Container 跑計算；
總覽頁以 AppTest 跑 views/overview.py，並以內層連線的 spy 記錄實際打到資料庫的語句。
"""

# ==== 原生（標準庫） ====
from pathlib import Path

# ==== 第三方套件 ====
import libsql
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.repositories.connection_layers import CountingConnection
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.query_metrics import QueryMetrics
from asset_lab.repositories.read_cache import ReadCache
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository

APP_DIR = Path(__file__).resolve().parent.parent
_MONTHS = ("2026-01", "2026-02", "2026-03", "2026-04")


def _seed(conn) -> None:
    """多月份、多種項目類型的虛構種子資料。"""
    SchemaRepository(conn=conn).ensure_schema()
    holding_repo = HoldingRepository(conn=conn)
    record_repo = RecordRepository(conn=conn)
    stock_id = holding_repo.add_holding(
        holding=HoldingModel(
            name="範例股票",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_market_value=300000.0,
            initial_cost=300000.0,
        )
    )
    deposit_id = holding_repo.add_holding(
        holding=HoldingModel(
            name="範例活存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.DEMAND_DEPOSIT,
            initial_market_value=100000.0,
            initial_cost=100000.0,
        )
    )
    for index, month in enumerate(_MONTHS):
        record_repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=stock_id,
                year_month=month,
                market_value=300000.0 + index * 10000.0 - (index == 3) * 60000.0,
                net_investment=0.0,
                total_cost=300000.0,
                realized_income=0.0,
            )
        )
        record_repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=deposit_id,
                year_month=month,
                market_value=100000.0 + index * 1000.0,
                net_investment=1000.0,
            )
        )


def _container(conn, *, with_cache: bool):
    """with_cache=False 時只經計數層，等於沒有快取。"""
    container = bootstrap.build_container(
        conn=conn, read_cache=ReadCache(ttl_seconds=300), query_metrics=QueryMetrics()
    )
    if with_cache:
        return container
    counted = CountingConnection(inner=conn, metrics=QueryMetrics())
    return bootstrap.Container(
        **{
            **{name: getattr(container, name) for name in container.__dataclass_fields__},
            "holding_repo": HoldingRepository(conn=counted),
            "record_repo": RecordRepository(conn=counted),
        }
    )


def _snapshot(container) -> dict[str, object]:
    """淨值、報酬率、配置、協定等級等計算輸出。"""
    holdings = container.holding_repo.list_holdings()
    range_df = container.record_repo.read_range(start_ym="0000-00", end_ym=_MONTHS[-1])
    series = container.return_service.cumulative_twr_series(range_df=range_df, holdings=holdings)
    thresholds = container.protocol_service.effective_thresholds(
        stored=container.protocol_threshold_repo.read_thresholds()
    )
    status = container.protocol_service.assess(
        series=series, thresholds=thresholds, min_data_months=2
    )
    net_worth = container.allocation_service.net_worth_series(range_df=range_df, holdings=holdings)
    return {
        "holdings": [h.model_dump() for h in holdings],
        "all_records": container.record_repo.read_all(),
        "range_records": range_df,
        "twr": series,
        "status": status,
        "net_worth": net_worth,
        "latest": container.record_repo.latest_year_month(),
    }


def _assert_same(actual: dict[str, object], expected: dict[str, object]) -> None:
    """DataFrame 欄位含 NaN，用 assert_frame_equal 逐項比較，其餘用相等。"""
    assert actual.keys() == expected.keys()
    for name, value in expected.items():
        if isinstance(value, pd.DataFrame):
            pd.testing.assert_frame_equal(actual[name], value)
        else:
            assert actual[name] == value, name


@pytest.mark.scenario("SC-119")
def test_sc119_cached_and_uncached_calculations_are_identical() -> None:
    conn = libsql.connect(":memory:")
    _seed(conn)
    uncached = _snapshot(_container(conn, with_cache=False))
    cached_container = _container(conn, with_cache=True)

    cold = _snapshot(cached_container)
    warm = _snapshot(cached_container)  # 第二次全部命中快取

    _assert_same(cold, uncached)
    _assert_same(warm, uncached)


@pytest.mark.scenario("SC-119")
def test_sc119_caller_mutating_dataframe_does_not_leak_into_other_callers() -> None:
    conn = libsql.connect(":memory:")
    _seed(conn)
    container = _container(conn, with_cache=True)
    first = container.record_repo.read_all()
    expected = first.copy()

    first["market_value"] = 0.0
    first.drop(first.index, inplace=True)

    pd.testing.assert_frame_equal(container.record_repo.read_all(), expected)


class _SpyConnection:
    """記錄實際打到資料庫的 (sql, params) 的內層連線。"""

    def __init__(self, real) -> None:
        self._real = real
        self.executed: list[tuple[str, tuple]] = []

    def cursor(self):
        spy = self

        class _Cursor:
            def __init__(self) -> None:
                self._cursor = spy._real.cursor()

            def execute(self, sql, parameters=()):
                spy.executed.append((sql, tuple(parameters)))
                self._cursor.execute(sql, parameters)
                return self

            def fetchall(self):
                return self._cursor.fetchall()

            def fetchone(self):
                return self._cursor.fetchone()

            @property
            def lastrowid(self):
                return self._cursor.lastrowid

        return _Cursor()

    def commit(self) -> None:
        self._real.commit()

    def rollback(self) -> None:
        self._real.rollback()


def _run_overview(spy: _SpyConnection, *, with_cache: bool) -> AppTest:
    metrics = QueryMetrics()
    if with_cache:
        container = bootstrap.build_container(
            conn=spy, read_cache=ReadCache(ttl_seconds=300), query_metrics=metrics
        )
    else:
        # 對照組：Repository 直接接計數層，沒有快取
        counted = CountingConnection(inner=spy, metrics=metrics)
        base = bootstrap.build_container(
            conn=spy, read_cache=ReadCache(ttl_seconds=300), query_metrics=metrics
        )
        container = bootstrap.Container(
            **{
                **{name: getattr(base, name) for name in base.__dataclass_fields__},
                "holding_repo": HoldingRepository(conn=counted),
                "record_repo": RecordRepository(conn=counted),
            }
        )
    at = AppTest.from_file(APP_DIR / "views" / "overview.py", default_timeout=15)
    at.session_state["container"] = container
    at.run()
    assert not at.exception
    return at


@pytest.mark.scenario("SC-118")
def test_sc118_duplicate_reads_in_one_cold_rerun_hit_database_once() -> None:
    real = libsql.connect(":memory:")
    _seed(real)

    # 對照：沒有快取時，總覽頁在同一次重跑內確實重複送出相同查詢
    control = _SpyConnection(real)
    _run_overview(control, with_cache=False)
    assert len(control.executed) > len(set(control.executed))

    spy = _SpyConnection(real)
    _run_overview(spy, with_cache=True)

    # 冷快取的一次整頁重跑：每個不同的 (sql, 參數) 只往返一次
    assert spy.executed
    assert len(spy.executed) == len(set(spy.executed))
    # 條件不同的查詢（全部紀錄與區間）各自往返，不被誤判為重複
    sqls = [sql for sql, _ in spy.executed]
    assert any("BETWEEN" in sql for sql in sqls)


@pytest.mark.scenario("SC-118")
def test_sc118_write_commit_between_reads_forces_a_fresh_read() -> None:
    real = libsql.connect(":memory:")
    _seed(real)
    spy = _SpyConnection(real)
    container = bootstrap.build_container(
        conn=spy, read_cache=ReadCache(ttl_seconds=300), query_metrics=QueryMetrics()
    )
    container.holding_repo.list_holdings()
    container.holding_repo.list_holdings()
    assert len(spy.executed) == 1

    container.holding_repo.add_holding(
        holding=HoldingModel(
            name="新增項目", kind=HOLDING_KIND.ASSET, category=ASSET_CATEGORIES.DEMAND_DEPOSIT
        )
    )
    spy.executed.clear()
    names = [h.name for h in container.holding_repo.list_holdings()]

    assert "新增項目" in names
    assert len([s for s, _ in spy.executed if s.lstrip().upper().startswith("SELECT")]) == 1
