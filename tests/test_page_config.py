"""瀏覽器分頁標題與圖示固定不隨頁面切換的回歸測試（SC-041）。

背景：`st.navigation` 預設會以當前頁的 `st.Page(title=...)` 當瀏覽器分頁標題，導致切頁時
分頁標籤跟著變。修法是在 `app.py` 頂層（整支腳本第一個 Streamlit 指令）呼叫
`st.set_page_config(page_title="資產管理", page_icon="💰")`；由於每次 rerun（含切頁、
登入前後）都會重新執行到這行並帶入相同值，分頁標題與圖示因而固定。

AppTest 的公開介面（ElementTree）只解析 delta 訊息，不含 `page_config_changed`；要驗證
分頁標題與圖示是否真的固定，需讀取底層 ForwardMsg 佇列。做法是攔截 AppTest 內部建立的
`LocalScriptRunner` 實例（monkeypatch 其類別引用），取得其 `forward_msgs()`。

側欄「切換頁面」需要放行（已登入本人）才能進入 st.navigation 路由，而放行後會組裝依賴
容器（含真實 Turso 連線），不適合在無網路的單元測試環境驅動。因此以下用兩種可在無網路
環境驗證、且已涵蓋所有會渲染畫面分支的情境（未登入、非本人被拒絕）驗證分頁設定固定，
另外用原始碼層級測試防止任何頁面檔重新引入覆蓋（回歸防線，函式較短故省略行為型 docstring）。
"""

# ==== 原生（標準庫） ====
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
import pytest
import streamlit.testing.v1.app_test as app_test_module
from streamlit.testing.v1.app_test import AppTest
from streamlit.testing.v1.local_script_runner import LocalScriptRunner

# ==== 專案內部 ====
# 無

APP_DIR = Path(__file__).resolve().parent.parent

FIXED_TITLE = "資產管理"
FIXED_FAVICON = "emoji:💰"

STRANGER_EMAIL = "stranger@example.test"
ALLOWED = frozenset({"owner@example.test"})


class _CapturingRunner(LocalScriptRunner):
    """記錄每個被建立的 LocalScriptRunner 實例，供測試讀取其原始 ForwardMsg 佇列。"""

    instances: list["_CapturingRunner"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        _CapturingRunner.instances.append(self)


def _run_with_capture(app: AppTest) -> AppTest:
    """以攔截版 LocalScriptRunner 執行 AppTest，讓 forward_msgs() 可被取用。"""
    _CapturingRunner.instances.clear()
    with mock.patch.object(app_test_module, "LocalScriptRunner", _CapturingRunner):
        app.run()
    return app


def _latest_page_config_msg():
    """取得最近一次 script run 送出的最後一筆 page_config_changed 訊息。"""
    runner = _CapturingRunner.instances[-1]
    page_config_msgs = [
        msg.page_config_changed
        for msg in runner.forward_msgs()
        if msg.HasField("page_config_changed")
    ]
    assert page_config_msgs, "app.py 應在每次 rerun 呼叫 st.set_page_config"
    return page_config_msgs[-1]


@pytest.mark.scenario("SC-041")
def test_login_screen_has_fixed_page_config():
    # 未登入：顯示登入畫面，分頁標題與圖示仍應是固定值
    with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=ALLOWED):
        app = _run_with_capture(AppTest.from_file("app.py", default_timeout=8))
    assert not app.exception

    cfg = _latest_page_config_msg()
    assert cfg.title == FIXED_TITLE
    assert cfg.favicon == FIXED_FAVICON


@pytest.mark.scenario("SC-041")
def test_denied_screen_has_fixed_page_config():
    # 已登入但非允許清單內的本人：顯示拒絕畫面，分頁標題與圖示仍應是固定值
    import streamlit as st

    stranger = SimpleNamespace(is_logged_in=True, email=STRANGER_EMAIL)
    with (
        mock.patch("asset_lab.bootstrap.allowed_emails", return_value=ALLOWED),
        mock.patch.object(st, "user", stranger),
    ):
        app = _run_with_capture(AppTest.from_file("app.py", default_timeout=8))
    assert not app.exception

    cfg = _latest_page_config_msg()
    assert cfg.title == FIXED_TITLE
    assert cfg.favicon == FIXED_FAVICON


@pytest.mark.scenario("SC-041")
def test_view_files_do_not_override_page_config():
    # 任一頁面檔若自行呼叫 set_page_config，會蓋掉入口固定的分頁標題／圖示：回歸防線
    for view_file in (APP_DIR / "views").glob("*.py"):
        assert "set_page_config" not in view_file.read_text(encoding="utf-8"), (
            f"{view_file.name} 不得呼叫 set_page_config，否則會覆蓋固定的分頁標題"
        )
