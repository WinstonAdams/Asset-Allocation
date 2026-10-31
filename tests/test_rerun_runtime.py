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
from asset_lab.repositories.read_cache import ReadCache
from asset_lab.rerun_runtime import (
    CONTAINER_SESSION_KEY,
    rerun_fragment,
    rerun_scope,
    verified_container,
)

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


# === verified_container：每次執行最多探測一次、入口做 TTL 判定 ===


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def probe_env():
    """替換 bootstrap 的探測入口與讀取快取，並以空 session_state 取代 st.session_state。"""
    clock = _FakeClock()
    cache = ReadCache(ttl_seconds=300, clock=clock)
    container = SimpleNamespace(name="container")
    calls: list[str] = []

    def _probe():
        calls.append("probe")
        return container

    original_expire = cache.expire_if_stale

    def _expire():
        calls.append("expire")
        return original_expire()

    cache.expire_if_stale = _expire
    session: dict = {}
    with mock.patch("asset_lab.bootstrap.get_resilient_container", side_effect=_probe) as probe, \
         mock.patch("asset_lab.bootstrap.get_read_cache", return_value=cache), \
         mock.patch.object(st, "session_state", session):
        yield SimpleNamespace(
            clock=clock, cache=cache, container=container, calls=calls, probe=probe, session=session
        )


def _scope(metrics: QueryMetrics | None = None):
    return rerun_scope(kind=RERUN_KIND.FULL, metrics=metrics or QueryMetrics())


@pytest.mark.scenario("SC-108")
def test_sc108_verified_container_probes_once_per_execution(probe_env) -> None:
    with _scope():
        first = verified_container()
        second = verified_container()
        third = verified_container()

    assert first is second is third is probe_env.container
    probe_env.probe.assert_called_once_with()


@pytest.mark.scenario("SC-111")
def test_sc111_callback_probe_before_scope_is_reused_by_the_page_rerun(probe_env) -> None:
    # 勾選 callback 在腳本主體之前執行（scope 之外）先探測；
    # 接著頁面重跑進入最外層 scope 再取容器，同一輪合計只探測一次
    from_callback = verified_container()
    with _scope():
        from_page = verified_container()
        verified_container()

    assert from_callback is from_page is probe_env.container
    probe_env.probe.assert_called_once_with()
    # 這一輪結束後暫存清掉，下一輪才重新探測
    with _scope():
        verified_container()
    assert probe_env.probe.call_count == 2


@pytest.mark.scenario("SC-108")
def test_sc108_verified_container_writes_session_state_every_call(probe_env) -> None:
    with _scope():
        verified_container()
        probe_env.session.clear()
        verified_container()

    assert probe_env.session[CONTAINER_SESSION_KEY] is probe_env.container


@pytest.mark.scenario("SC-108")
def test_sc108_each_new_execution_probes_again(probe_env) -> None:
    with _scope():
        verified_container()
    with _scope():
        verified_container()

    assert probe_env.probe.call_count == 2


@pytest.mark.scenario("SC-108")
def test_sc108_nested_scope_exit_keeps_the_execution_result(probe_env) -> None:
    # 整頁重跑裡的 fragment（巢狀 scope）結束，不能讓外層後續呼叫重新探測
    with _scope():
        verified_container()
        with rerun_scope(kind=RERUN_KIND.FRAGMENT, metrics=QueryMetrics()):
            verified_container()
        verified_container()

    probe_env.probe.assert_called_once_with()


@pytest.mark.scenario("SC-108")
def test_sc108_result_is_cleared_even_when_the_scope_is_interrupted(probe_env) -> None:
    with pytest.raises(_Interrupt):
        with _scope():
            verified_container()
            raise _Interrupt
    with _scope():
        verified_container()

    assert probe_env.probe.call_count == 2


@pytest.mark.scenario("SC-110")
def test_sc110_probe_failure_propagates_and_is_not_cached(probe_env) -> None:
    probe_env.probe.side_effect = [ValueError("boom"), probe_env.container]

    with _scope():
        with pytest.raises(ValueError, match="boom"):
            verified_container()
        assert CONTAINER_SESSION_KEY not in probe_env.session
        assert verified_container() is probe_env.container

    assert probe_env.probe.call_count == 2


@pytest.mark.scenario("SC-115")
def test_sc115_expiry_checked_once_at_entry_after_probe(probe_env) -> None:
    with _scope():
        verified_container()
        verified_container()

    assert probe_env.calls == ["probe", "expire"]


@pytest.mark.scenario("SC-115")
def test_sc115_entry_at_299_keeps_cache_and_at_300_clears_whole_batch(probe_env) -> None:
    cache, clock = probe_env.cache, probe_env.clock
    key_a, key_b = ("SELECT a", ()), ("SELECT b", ())
    cache.put(key_a, [(1,)], generation=cache.generation())
    cache.put(key_b, [(2,)], generation=cache.generation())
    clock.now += 299
    with _scope():
        verified_container()
    assert cache.get(key_a) == [(1,)] and cache.get(key_b) == [(2,)]

    clock.now += 1
    with _scope():
        verified_container()

    assert cache.get(key_a) is None and cache.get(key_b) is None


@pytest.mark.scenario("SC-115")
def test_sc115_no_expiry_check_inside_the_same_execution(probe_env) -> None:
    # 同一次重跑內不逐筆判定：進入後時間走過 TTL，這次執行仍看到同一批資料
    cache, clock = probe_env.cache, probe_env.clock
    key = ("SELECT a", ())
    cache.put(key, [(1,)], generation=cache.generation())
    with _scope():
        verified_container()
        clock.now += 400
        verified_container()
        assert cache.get(key) == [(1,)]


@pytest.mark.scenario("SC-115")
def test_sc115_expiry_not_checked_when_probe_fails(probe_env) -> None:
    probe_env.probe.side_effect = ValueError("boom")

    with _scope():
        with pytest.raises(ValueError):
            verified_container()

    assert "expire" not in probe_env.calls


# === rerun_fragment：st.fragment → rerun_scope → error_boundary → verified_container ===

FRAGMENT_LABEL = "測試編輯器"


def _fragment_script(mode: str) -> None:
    import streamlit as st

    from asset_lab.core.exceptions import PersistenceError
    from asset_lab.rerun_runtime import rerun_fragment

    @rerun_fragment(label="測試編輯器")
    def editor(*, target_ym: str) -> None:
        st.write(f"編輯器 {target_ym}")
        if mode == "unexpected":
            raise RuntimeError("libsql native error at /srv/app/secret_path.py")
        if mode == "domain":
            raise PersistenceError("存檔失敗，資料未變更，請重試")
        if mode == "rerun":
            st.session_state["reruns"] = st.session_state.get("reruns", 0) + 1
            if st.session_state["reruns"] == 1:
                st.rerun()

    editor(target_ym="2026-09")


@pytest.fixture
def fragment_env():
    """fragment 入口用的連線探測替身；回傳可檢查探測次數的替身組。"""
    container = SimpleNamespace(name="container")
    cache = SimpleNamespace(expire_if_stale=lambda: None)
    with mock.patch(
        "asset_lab.bootstrap.get_resilient_container", return_value=container
    ) as probe, mock.patch("asset_lab.bootstrap.get_read_cache", return_value=cache), \
         mock.patch("asset_lab.bootstrap.get_query_metrics", return_value=QueryMetrics()):
        yield SimpleNamespace(container=container, probe=probe)


def _run_fragment(mode: str) -> AppTest:
    return AppTest.from_function(_fragment_script, args=(mode,), default_timeout=8).run()


@pytest.mark.scenario("SC-120")
def test_sc120_fragment_verifies_connection_before_running_the_body(fragment_env) -> None:
    app = _run_fragment("ok")

    assert not app.exception
    assert [m.value for m in app.markdown] == ["編輯器 2026-09"]
    fragment_env.probe.assert_called_once_with()
    assert app.session_state[CONTAINER_SESSION_KEY] is fragment_env.container


@pytest.mark.scenario("SC-120")
@pytest.mark.scenario("SC-131")
def test_sc131_fragment_run_logs_exactly_one_fragment_line(fragment_env, caplog) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _run_fragment("ok")

    records = _metric_records(caplog)
    assert len(records) == 1
    match = LINE_PATTERN.match(records[0].getMessage())
    assert match
    assert match["kind"] == RERUN_KIND.FRAGMENT
    assert match["page"] == FRAGMENT_LABEL
    assert match["interrupted"] == "false"


@pytest.mark.scenario("SC-122")
def test_sc122_domain_error_inside_fragment_shows_friendly_message(fragment_env, caplog) -> None:
    with caplog.at_level(logging.ERROR):
        app = _run_fragment("domain")

    assert not app.exception
    assert [e.value for e in app.error] == ["存檔失敗，資料未變更，請重試"]
    assert "領域錯誤" in caplog.text


@pytest.mark.scenario("SC-122")
def test_sc122_unexpected_error_inside_fragment_shows_generic_message(
    fragment_env, caplog
) -> None:
    original = st.get_option("client.showErrorDetails")
    st.set_option("client.showErrorDetails", "none")
    try:
        with caplog.at_level(logging.ERROR):
            app = _run_fragment("unexpected")
    finally:
        st.set_option("client.showErrorDetails", original)

    assert not app.exception
    assert [e.value for e in app.error] == ["發生未預期錯誤，請稍後再試"]
    assert "secret_path" not in "".join(str(e.value) for e in app.error)
    assert "secret_path" in caplog.text


@pytest.mark.scenario("SC-121")
@pytest.mark.scenario("SC-131")
def test_sc131_st_rerun_inside_fragment_is_not_swallowed_and_marks_interrupted(
    fragment_env, caplog
) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        app = _run_fragment("rerun")

    assert not app.exception
    assert not app.error
    records = _metric_records(caplog)
    interrupted = [r.getMessage().split("interrupted=")[1] for r in records]
    # 存檔那次被 st.rerun 中斷記一行，接著的重跑再記一行，兩行都是 fragment 類型
    assert interrupted == ["true", "false"]
    assert all("kind=fragment" in r.getMessage() for r in records)


@pytest.mark.scenario("SC-120")
def test_sc120_fragment_preserves_wrapped_function_identity(fragment_env) -> None:
    # Streamlit 以 __module__／__qualname__ 計算 fragment id，裝飾後必須保留
    @rerun_fragment(label=FRAGMENT_LABEL)
    def sample_editor() -> None:
        return None

    assert getattr(sample_editor, "__name__", None) == "sample_editor"
    assert "sample_editor" in getattr(sample_editor, "__qualname__", "")
