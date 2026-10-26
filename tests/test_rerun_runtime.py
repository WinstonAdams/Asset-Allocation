"""rerun_scope：每次執行記一行量測 log（SC-130）。"""

# ==== 原生（標準庫） ====
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import RERUN_KIND
from asset_lab.repositories.query_metrics import QueryMetrics
from asset_lab.rerun_runtime import rerun_scope

APP_DIR = Path(__file__).resolve().parent.parent
LOGGER_NAME = "asset_lab.rerun_runtime"
LINE_PATTERN = re.compile(
    r"^重跑量測 kind=(?P<kind>\S+) page=(?P<page>\S+) elapsed_ms=(?P<elapsed>\d+) "
    r"db_roundtrips=(?P<trips>\d+) cache_hits=(?P<hits>\d+) "
    r"reconnected=(?P<reconnected>true|false) interrupted=(?P<interrupted>true|false)$"
)


class _Interrupt(BaseException):
    """模擬 st.stop()／st.rerun() 的控制例外（BaseException 子類）。"""


def _metric_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == LOGGER_NAME and r.getMessage().startswith("重跑量測")
    ]


@pytest.mark.scenario("SC-130")
def test_sc130_outermost_scope_logs_exactly_one_line_with_all_fields(caplog) -> None:
    metrics = QueryMetrics()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics, page="總覽"):
            metrics.add_roundtrip()
            metrics.add_roundtrip()
            metrics.add_cache_hit()

    records = _metric_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    match = LINE_PATTERN.match(records[0].getMessage())
    assert match, records[0].getMessage()
    assert match["kind"] == "full"
    assert match["page"] == "總覽"
    assert match["trips"] == "2"
    assert match["hits"] == "1"
    assert match["reconnected"] == "false"
    assert match["interrupted"] == "false"


@pytest.mark.scenario("SC-130")
def test_sc130_unknown_page_is_logged_as_dash(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=QueryMetrics()):
            pass

    match = LINE_PATTERN.match(_metric_records(caplog)[0].getMessage())
    assert match and match["page"] == "-"


@pytest.mark.scenario("SC-130")
def test_sc130_page_can_be_assigned_inside_the_scope(caplog) -> None:
    # app.py 要到 st.navigation 之後才知道頁面名稱
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=QueryMetrics()) as scope:
            scope.page = "資產配置"

    match = LINE_PATTERN.match(_metric_records(caplog)[0].getMessage())
    assert match and match["page"] == "資產配置"


@pytest.mark.scenario("SC-130")
def test_sc130_roundtrips_before_the_scope_count_into_the_same_line(caplog) -> None:
    # 勾選 callback 等在腳本之前產生的往返，必須算進同一次執行的那一行
    metrics = QueryMetrics()
    metrics.add_roundtrip()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics):
            metrics.add_roundtrip()

    match = LINE_PATTERN.match(_metric_records(caplog)[0].getMessage())
    assert match and match["trips"] == "2"


@pytest.mark.scenario("SC-130")
def test_sc130_counters_reset_after_each_execution(caplog) -> None:
    metrics = QueryMetrics()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics):
            metrics.add_roundtrip()
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics):
            pass

    second = LINE_PATTERN.match(_metric_records(caplog)[1].getMessage())
    assert second and second["trips"] == "0"


@pytest.mark.scenario("SC-130")
def test_sc130_nested_scope_does_not_log_separately(caplog) -> None:
    metrics = QueryMetrics()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics, page="外") as outer:
            assert outer.is_outermost is True
            with rerun_scope(kind=RERUN_KIND.FRAGMENT, metrics=metrics, page="內") as inner:
                assert inner.is_outermost is False
                metrics.add_roundtrip()

    records = _metric_records(caplog)
    assert len(records) == 1
    match = LINE_PATTERN.match(records[0].getMessage())
    assert match and match["kind"] == "full" and match["page"] == "外" and match["trips"] == "1"


@pytest.mark.scenario("SC-130")
def test_sc130_scope_after_nested_one_is_outermost_again(caplog) -> None:
    metrics = QueryMetrics()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics):
            pass
        with rerun_scope(kind=RERUN_KIND.FRAGMENT, metrics=metrics, page="編輯器") as scope:
            assert scope.is_outermost is True

    assert [LINE_PATTERN.match(r.getMessage())["kind"] for r in _metric_records(caplog)] == [
        "full",
        "fragment",
    ]


@pytest.mark.scenario("SC-130")
def test_sc130_interrupted_by_control_exception_is_logged_and_reraised(caplog) -> None:
    # st.stop()／st.rerun() 都是 BaseException：照記一行並標示被中斷，例外原樣往上拋
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with pytest.raises(_Interrupt):
            with rerun_scope(kind=RERUN_KIND.FULL, metrics=QueryMetrics()):
                raise _Interrupt

    records = _metric_records(caplog)
    assert len(records) == 1
    match = LINE_PATTERN.match(records[0].getMessage())
    assert match and match["interrupted"] == "true"


@pytest.mark.scenario("SC-130")
def test_sc130_interrupted_by_regular_exception_is_logged_and_reraised(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with pytest.raises(ValueError):
            with rerun_scope(kind=RERUN_KIND.FULL, metrics=QueryMetrics()):
                raise ValueError("x")

    match = LINE_PATTERN.match(_metric_records(caplog)[0].getMessage())
    assert match and match["interrupted"] == "true"


@pytest.mark.scenario("SC-130")
def test_sc130_reconnected_flag_is_reported(caplog) -> None:
    metrics = QueryMetrics()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics):
            metrics.mark_reconnected()

    match = LINE_PATTERN.match(_metric_records(caplog)[0].getMessage())
    assert match and match["reconnected"] == "true"


@pytest.mark.scenario("SC-130")
def test_sc130_log_line_contains_no_email(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with rerun_scope(kind=RERUN_KIND.FULL, metrics=QueryMetrics(), page="總覽"):
            pass

    assert "@" not in _metric_records(caplog)[0].getMessage()


@pytest.mark.scenario("SC-130")
def test_sc130_login_guard_stop_logs_one_interrupted_line_and_no_ui_metrics(caplog) -> None:
    # 登入守門 st.stop() 的那次整頁重跑也要記一行，標示被中斷；畫面不顯示任何量測資訊
    allowed = frozenset({"owner@example.test"})
    stranger = SimpleNamespace(is_logged_in=True, email="stranger@example.test")
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), \
         mock.patch("asset_lab.bootstrap.allowed_emails", return_value=allowed), \
         mock.patch.object(st, "user", stranger):
        app = AppTest.from_file(APP_DIR / "app.py", default_timeout=8).run()

    assert not app.exception
    records = _metric_records(caplog)
    assert len(records) == 1
    match = LINE_PATTERN.match(records[0].getMessage())
    assert match and match["kind"] == "full" and match["interrupted"] == "true"
    assert "stranger@example.test" not in records[0].getMessage()
    # 畫面上沒有量測文字
    rendered = [e.value for e in app.error]
    rendered += [t.value for t in app.title] + [m.value for m in app.markdown]
    assert not any("重跑量測" in text for text in rendered)
