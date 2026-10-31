"""error_boundary：未預期錯誤通用訊息、開關開啟原樣往上拋、領域錯誤維持原訊息（SC-123/125/126），
以及 widget callback 的 guarded_callback（SC-127）。"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import ERROR_DETAILS
from asset_lab.error_boundary import (
    CALLBACK_ERROR_SESSION_KEY,
    UNEXPECTED_ERROR_MESSAGE,
    error_details_enabled,
    guarded_callback,
)

OPTION = "client.showErrorDetails"
LOGGER_NAME = "asset_lab.error_boundary"
RAW_SECRET_TEXT = "libsql native error at /srv/app/secret_path.py"


@pytest.fixture(autouse=True)
def restore_error_details_option():
    """st.set_option 是程序全域設定，測試後還原。"""
    original = st.get_option(OPTION)
    yield
    st.set_option(OPTION, original)


def _raising_script(mode: str, error_kind: str) -> None:
    import streamlit as st

    from asset_lab.core.exceptions import PersistenceError
    from asset_lab.error_boundary import error_boundary

    st.set_option("client.showErrorDetails", mode)
    with error_boundary(context="test-ctx"):
        if error_kind == "unexpected":
            raise RuntimeError("libsql native error at /srv/app/secret_path.py")
        if error_kind == "domain":
            raise PersistenceError("存檔失敗，資料未變更，請重試")
        st.write("正常內容")


def _run(mode: str, error_kind: str) -> AppTest:
    return AppTest.from_function(
        _raising_script, args=(mode, error_kind), default_timeout=8
    ).run()


@pytest.mark.scenario("SC-123")
def test_sc123_unexpected_error_shows_only_generic_message(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        app = _run(ERROR_DETAILS.HIDE, "unexpected")

    assert not app.exception
    assert [e.value for e in app.error] == [UNEXPECTED_ERROR_MESSAGE]
    assert RAW_SECRET_TEXT not in UNEXPECTED_ERROR_MESSAGE
    assert all(RAW_SECRET_TEXT not in str(e.value) for e in app.error)


@pytest.mark.scenario("SC-123")
def test_sc123_unexpected_error_details_go_to_log(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        _run(ERROR_DETAILS.HIDE, "unexpected")

    records = [r for r in caplog.records if r.name == LOGGER_NAME]
    assert len(records) == 1
    assert "test-ctx" in records[0].getMessage()
    assert records[0].exc_info is not None
    assert RAW_SECRET_TEXT in str(records[0].exc_info[1])


@pytest.mark.scenario("SC-123")
def test_sc123_normal_flow_untouched(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        app = _run(ERROR_DETAILS.HIDE, "none")

    assert not app.exception
    assert not app.error
    assert not [r for r in caplog.records if r.name == LOGGER_NAME]


def _stop_script() -> None:
    import streamlit as st

    from asset_lab.error_boundary import error_boundary

    with error_boundary(context="test-ctx"):
        st.write("before")
        st.stop()
    st.write("unreachable")


@pytest.mark.scenario("SC-123")
def test_sc123_st_stop_is_not_treated_as_error(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        app = AppTest.from_function(_stop_script, default_timeout=8).run()

    assert not app.exception
    assert not app.error
    assert not [r for r in caplog.records if r.name == LOGGER_NAME]


def _interrupt_script() -> None:
    from asset_lab.error_boundary import error_boundary

    class Control(BaseException):
        pass

    try:
        with error_boundary(context="test-ctx"):
            raise Control
    except Control:
        import streamlit as st

        st.write("控制例外原樣穿過")


@pytest.mark.scenario("SC-123")
def test_sc123_base_exception_passes_through():
    app = AppTest.from_function(_interrupt_script, default_timeout=8).run()

    assert not app.exception
    assert not app.error
    assert [m.value for m in app.markdown] == ["控制例外原樣穿過"]


def _fragment_handled_script() -> None:
    from streamlit.errors import FragmentHandledException

    from asset_lab.error_boundary import error_boundary

    with error_boundary(context="test-ctx"):
        raise FragmentHandledException("already shown")


@pytest.mark.scenario("SC-123")
def test_sc123_fragment_handled_exception_is_not_rewrapped(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        app = AppTest.from_function(_fragment_handled_script, default_timeout=8).run()

    assert UNEXPECTED_ERROR_MESSAGE not in [e.value for e in app.error]
    assert not [r for r in caplog.records if r.name == LOGGER_NAME]


@pytest.mark.scenario("SC-125")
def test_sc125_details_enabled_reraises_for_full_error_screen(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        app = _run(ERROR_DETAILS.SHOW, "unexpected")

    # 原樣往上拋：交給 Streamlit 的完整錯誤畫面，不改寫成通用訊息
    assert len(app.exception) == 1
    assert UNEXPECTED_ERROR_MESSAGE not in [e.value for e in app.error]
    records = [r for r in caplog.records if r.name == LOGGER_NAME]
    assert len(records) == 1


@pytest.mark.scenario("SC-125")
def test_sc125_error_details_enabled_reads_streamlit_option():
    st.set_option(OPTION, ERROR_DETAILS.SHOW)
    assert error_details_enabled() is True
    st.set_option(OPTION, ERROR_DETAILS.HIDE)
    assert error_details_enabled() is False


@pytest.mark.scenario("SC-126")
@pytest.mark.parametrize("mode", [ERROR_DETAILS.HIDE, ERROR_DETAILS.SHOW])
def test_sc126_domain_error_keeps_its_own_message(mode, caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        app = _run(mode, "domain")

    assert not app.exception
    assert [e.value for e in app.error] == ["存檔失敗，資料未變更，請重試"]
    records = [r for r in caplog.records if r.name == LOGGER_NAME]
    assert len(records) == 1
    assert records[0].exc_info is not None


def _callback_script(mode: str, error_kind: str) -> None:
    import streamlit as st

    from asset_lab.core.exceptions import PersistenceError
    from asset_lab.error_boundary import guarded_callback, show_callback_error

    st.set_option("client.showErrorDetails", mode)

    @guarded_callback(context="test-cb")
    def on_click_handler():
        if error_kind == "unexpected":
            raise RuntimeError("libsql native error at /srv/app/secret_path.py")
        if error_kind == "domain":
            raise PersistenceError("存檔失敗，資料未變更，請重試")
        st.session_state["handled"] = True

    st.title("測試頁")
    show_callback_error()
    st.button("go", key="go", on_click=on_click_handler)
    st.write("頁面已渲染")


def _click_go(mode: str, error_kind: str) -> AppTest:
    app = AppTest.from_function(_callback_script, args=(mode, error_kind), default_timeout=8)
    app.run()
    return app.button(key="go").click().run()


@pytest.mark.scenario("SC-127")
def test_sc127_unexpected_callback_error_shows_generic_message_below_title(caplog):
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        app = _click_go(ERROR_DETAILS.HIDE, "unexpected")

    assert not app.exception
    assert [e.value for e in app.error] == [UNEXPECTED_ERROR_MESSAGE]
    # 頁面照常渲染，訊息在標題之後（以主區元素順序斷言）
    assert [m.value for m in app.markdown if m.value == "頁面已渲染"] == ["頁面已渲染"]
    order = [el.type for el in app.main]
    assert order.index("title") < order.index("error")
    assert all(RAW_SECRET_TEXT not in str(e.value) for e in app.error)
    records = [r for r in caplog.records if r.name == LOGGER_NAME]
    assert len(records) == 1
    assert "test-cb" in records[0].getMessage()
    assert RAW_SECRET_TEXT in str(records[0].exc_info[1])


@pytest.mark.scenario("SC-127")
def test_sc127_callback_error_message_is_shown_once_then_cleared():
    app = _click_go(ERROR_DETAILS.HIDE, "unexpected")
    assert len(app.error) == 1

    app.run()

    assert not app.error
    assert CALLBACK_ERROR_SESSION_KEY not in app.session_state


@pytest.mark.scenario("SC-127")
@pytest.mark.parametrize("mode", [ERROR_DETAILS.HIDE, ERROR_DETAILS.SHOW])
def test_sc127_domain_callback_error_keeps_its_own_message(mode):
    app = _click_go(mode, "domain")

    assert not app.exception
    assert [e.value for e in app.error] == ["存檔失敗，資料未變更，請重試"]


@pytest.mark.scenario("SC-127")
def test_sc127_details_enabled_reraises_unexpected_callback_error():
    app = _click_go(ERROR_DETAILS.SHOW, "unexpected")

    # 本機除錯：原樣往上拋，不改寫成通用訊息
    assert len(app.exception) == 1
    assert UNEXPECTED_ERROR_MESSAGE not in [e.value for e in app.error]


@pytest.mark.scenario("SC-127")
def test_sc127_normal_callback_has_no_message():
    app = _click_go(ERROR_DETAILS.HIDE, "none")

    assert not app.exception
    assert not app.error
    assert app.session_state["handled"] is True


@pytest.mark.scenario("SC-127")
def test_sc127_callback_decorator_passes_through_base_exception_and_metadata():
    class Control(BaseException):
        pass

    @guarded_callback(context="test-cb")
    def handler():
        """doc"""
        raise Control

    assert handler.__name__ == "handler"
    with pytest.raises(Control):
        handler()
