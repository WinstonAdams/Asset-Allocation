"""錯誤細節開關：環境變數解析（SC-124）、入口把結果套用到 Streamlit 設定、config.toml 兜底。"""

# ==== 原生（標準庫） ====
import tomllib
from pathlib import Path
from unittest import mock

# ==== 第三方套件 ====
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.constants import ERROR_DETAILS

APP_DIR = Path(__file__).resolve().parent.parent
OPTION = "client.showErrorDetails"


@pytest.fixture
def restore_error_details_option():
    """st.set_option 是程序全域設定，測試後還原以免污染其他測試。"""
    original = st.get_option(OPTION)
    yield
    st.set_option(OPTION, original)


@pytest.mark.scenario("SC-124")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", ERROR_DETAILS.SHOW),
        ("TRUE", ERROR_DETAILS.SHOW),
        (" Yes ", ERROR_DETAILS.SHOW),
        ("on", ERROR_DETAILS.SHOW),
        ("0", ERROR_DETAILS.HIDE),
        ("false", ERROR_DETAILS.HIDE),
        ("", ERROR_DETAILS.HIDE),
        ("enabled", ERROR_DETAILS.HIDE),
        (None, ERROR_DETAILS.HIDE),
    ],
)
def test_sc124_resolve_error_detail_mode(raw, expected):
    assert bootstrap.resolve_error_detail_mode(raw=raw) == expected


def _run_app_with_env(monkeypatch, value: str | None) -> AppTest:
    if value is None:
        monkeypatch.delenv(ERROR_DETAILS.ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ERROR_DETAILS.ENV_VAR, value)
    with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=frozenset()):
        return AppTest.from_file(APP_DIR / "app.py", default_timeout=8).run()


@pytest.mark.scenario("SC-124")
def test_sc124_app_applies_enabled_env_to_streamlit_option(
    monkeypatch, restore_error_details_option
):
    st.set_option(OPTION, ERROR_DETAILS.HIDE)
    _run_app_with_env(monkeypatch, " On ")
    assert st.get_option(OPTION) == ERROR_DETAILS.SHOW


@pytest.mark.scenario("SC-124")
def test_sc124_native_streamlit_setting_cannot_reveal_details(
    monkeypatch, restore_error_details_option
):
    # 即使 Streamlit 原生參數已設為 full，專案開關未開啟時仍被蓋回隱藏
    st.set_option(OPTION, ERROR_DETAILS.SHOW)
    _run_app_with_env(monkeypatch, None)
    assert st.get_option(OPTION) == ERROR_DETAILS.HIDE


@pytest.mark.scenario("SC-123")
def test_sc123_config_toml_hides_details_by_default():
    config = tomllib.loads((APP_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["client"]["showErrorDetails"] == "none"
