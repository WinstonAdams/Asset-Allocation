"""app.py 登入守門的 fail-closed 串接層回歸測試（SC-033 / SC-034）。

evaluate_access 的「判定」邏輯已由 test_access_control.py 純函式完整覆蓋；本檔補上
串接層的副作用契約：守門未放行時 app.py 必須在任何頁面渲染與依賴組裝之前 st.stop()，
使未登入 / 非本人看不到任何頁面內容或財務資料（fail-closed）。

以 Streamlit AppTest 實際跑 app.py 腳本：
- 未登入：AppTest 預設 st.user 無 is_logged_in → 退化為未登入 → 顯示登入入口並停止。
- 非本人：以替身 st.user（已登入但 email 不在允許清單）驅動 → 顯示拒絕並停止。

兩者皆斷言：未組裝依賴容器（未觸發任何資料讀取）、未進入多頁路由（無頁面內容）。
測試一律用虛構 email（遵守敏感資料護欄）。
"""

# ==== 原生（標準庫） ====
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
# 注意：不在模組層級 import app.py——app.py 在載入時即呼叫 main()（觸發 secrets 讀取），
# 只有透過 AppTest 在受控替身下執行才安全。守門放行後存依賴容器用的 session key 直接內聯
# （與 app.CONTAINER_SESSION_KEY 對齊），避免 import 時副作用。
CONTAINER_SESSION_KEY = "container"

OWNER_EMAIL = "owner@example.test"
STRANGER_EMAIL = "stranger@example.test"
ALLOWED = frozenset({OWNER_EMAIL})


def _app() -> AppTest:
    """以受控的允許清單載入 app.py（避免依賴本機 secrets 檔）。"""
    return AppTest.from_file("app.py", default_timeout=8)


class TestSc033NotLoggedInFailClosed:
    """SC-033：未登入前顯示登入入口，不渲染任何頁面、不載入任何財務資料。"""

    @pytest.mark.scenario("SC-033")
    def test_sc033_not_logged_in_shows_login_entry_and_stops(self):
        # 預設 st.user 未登入：應顯示登入入口（標題＋Google 登入鈕），不崩潰
        with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=ALLOWED):
            app = _app().run()
        assert not app.exception
        assert [t.value for t in app.title] == ["資產配置管理"]
        assert any("Google" in b.label for b in app.button)

    @pytest.mark.scenario("SC-033")
    def test_sc033_not_logged_in_does_not_assemble_container_or_route(self):
        # fail-closed：守門 st.stop() 前置於組裝與路由 → 未存入依賴容器、未渲染頁面內容
        with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=ALLOWED):
            app = _app().run()
        # 未組裝依賴容器（未觸發任何資料讀取）
        assert CONTAINER_SESSION_KEY not in app.session_state
        # 未進入多頁路由：畫面不含拒絕訊息以外的任何頁面內容（無 error、無側欄登入資訊）
        assert not app.error


class TestSc034StrangerFailClosed:
    """SC-034：非本人 email 登入後被擋下，不渲染任何頁面、不觸發任何財務資料讀取。"""

    @staticmethod
    def _stranger_user() -> SimpleNamespace:
        # 已登入但 email 不在允許清單的替身使用者
        return SimpleNamespace(is_logged_in=True, email=STRANGER_EMAIL)

    @pytest.mark.scenario("SC-034")
    def test_sc034_stranger_is_denied_and_stops(self):
        # 已登入但非本人：顯示「無權限」拒絕訊息並停止
        import streamlit as st

        with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=ALLOWED), \
             mock.patch.object(st, "user", self._stranger_user()):
            app = _app().run()
        assert not app.exception
        assert [t.value for t in app.title] == ["無權限"]
        # 拒絕訊息明確，不洩漏任何財務資料
        assert any("允許清單" in e.value for e in app.error)

    @pytest.mark.scenario("SC-034")
    def test_sc034_stranger_does_not_assemble_container_or_route(self):
        # fail-closed：非本人同樣在組裝與路由前停止 → 無依賴容器、無頁面內容
        import streamlit as st

        with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=ALLOWED), \
             mock.patch.object(st, "user", self._stranger_user()):
            app = _app().run()
        assert CONTAINER_SESSION_KEY not in app.session_state

    @pytest.mark.scenario("SC-034")
    def test_sc034_empty_allowlist_denies_logged_in_user(self):
        # 允許清單為空（如 secrets 未設定，fail-closed）：任何登入者皆被擋下
        import streamlit as st

        with mock.patch("asset_lab.bootstrap.allowed_emails", return_value=frozenset()), \
             mock.patch.object(st, "user", self._stranger_user()):
            app = _app().run()
        assert [t.value for t in app.title] == ["無權限"]
        assert CONTAINER_SESSION_KEY not in app.session_state
