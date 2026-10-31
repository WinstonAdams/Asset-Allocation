"""連線檢查往返次數：以 :memory: libsql 與真實分層跑 app.py，比較兩次執行的往返差值（SC-108）。"""

# ==== 原生（標準庫） ====
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
import libsql
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab import bootstrap

APP_DIR = Path(__file__).resolve().parent.parent
OWNER_EMAIL = "owner@example.test"


class _ConnectionProvider:
    """取代 bootstrap.get_connection：固定回傳同一條 :memory: 連線（可跨執行緒使用）。"""

    def __init__(self) -> None:
        self._conn = libsql.connect(":memory:")

    def __call__(self):
        return self._conn

    def clear(self) -> None:
        pass


@pytest.fixture
def logged_in_env():
    caches = (
        bootstrap.get_container,
        bootstrap.ensure_schema_once,
        bootstrap.get_read_cache,
        bootstrap.get_query_metrics,
    )
    for cache in caches:
        cache.clear()
    provider = _ConnectionProvider()
    owner = SimpleNamespace(is_logged_in=True, email=OWNER_EMAIL)
    with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=frozenset({OWNER_EMAIL})), \
         mock.patch.object(st, "user", owner), \
         mock.patch("asset_lab.bootstrap.get_connection", provider):
        yield provider
    for cache in caches:
        cache.clear()


@pytest.mark.scenario("SC-108")
def test_sc108_second_full_rerun_spends_exactly_one_roundtrip_on_the_connection_check(
    logged_in_env,
) -> None:
    app = AppTest.from_file(APP_DIR / "app.py", default_timeout=30).run()
    assert not app.exception
    metrics = bootstrap.get_query_metrics()

    before = metrics.total_roundtrips()
    app.run()
    after = metrics.total_roundtrips()

    assert not app.exception
    # 第二輪：建表已做過、頁面讀取全部命中快取，只剩一次 SELECT 1 探測
    assert after - before == 1


@pytest.mark.scenario("SC-108")
def test_sc108_first_run_builds_schema_so_it_costs_more_than_one_roundtrip(
    logged_in_env,
) -> None:
    metrics = bootstrap.get_query_metrics()
    before = metrics.total_roundtrips()

    AppTest.from_file(APP_DIR / "app.py", default_timeout=30).run()

    assert metrics.total_roundtrips() - before > 1
