"""Streamlit 入口：登入守門 → 依賴組裝 → 多頁路由。

以 `streamlit run app.py` 啟動常駐進程，每次互動觸發整個 script rerun（無批次語意、無
CLI 參數，故不採 RPA 的 main.py + argparse 模型）。本檔職責限於三件事：

1. 守門：未登入先顯示登入入口並停止；已登入則以純判定（evaluate_access）比對 st.user.email
   是否在允許清單，非本人即顯示拒絕並停止——前置於任何資料存取，確保非本人看不到任何
   財務資料。允許 email 與登入設定皆來自 st.secrets，不寫死。
2. 組裝：放行後取快取的依賴容器（連線與 schema 已就緒；連線因閒置逾時失效時
   `get_resilient_container()` 會自動清快取重連並重試一次，見 bootstrap.py），存入
   session 供各頁取用。
3. 路由：以 st.navigation 註冊多頁並執行當前頁。

實際業務運算與 I/O 已在下層 Service/Repository（由 SC 測試保證正確）；本檔只做守門副作用
與組裝路由，屬難以純單元測試的 Streamlit runtime 黏合。
"""

# ==== 原生（標準庫） ====
import os

# 規避 pyarrow 25 內建 mimalloc 配置器在 macOS arm64 的 thread-init segfault：
# Streamlit 顯示 DataFrame（st.dataframe / st.data_editor）時 pandas→Arrow 轉換走
# arrow::py::ConvertPySequence，恰好在新執行緒配置記憶體即整個 Python 進程 EXC_BAD_ACCESS
# 崩潰（使用者本機操作月度錄入編輯、切頁時實測重現）。ARROW_DEFAULT_MEMORY_POOL=system
# 停用 mimalloc、改用系統 malloc 後，同樣的壓力操作已驗證不再崩潰。
#
# 這行刻意置於 `import streamlit` 之前、且早於本檔其餘所有 import（打破一般「先 import
# 後執行程式碼」的慣例）：pyarrow 只在自身被 import 的當下讀取此環境變數一次，之後就
# 定案，而 Streamlit 一 import 就會連帶 import pyarrow，若這行晚於 `import streamlit`
# 才執行就已經來不及生效。這是本檔唯一允許「設定先於第三方 import」的例外，非隨意調整
# import 順序。用 setdefault 而非直接賦值，是為了不覆蓋使用者已透過部署環境明確設定的值。
os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.access import AccessReason, evaluate_access

# 固定瀏覽器分頁標題與圖示：st.set_page_config 必須是整支腳本第一個 Streamlit 指令，
# 且每次 rerun（包含切頁、登入前後）都會重新執行到這裡並帶入相同值，因此標題與圖示
# 不會被登入畫面、拒絕畫面或 st.navigation／各頁的 st.Page(title=...) 覆蓋——後者只影響
# 側邊欄導覽項目的顯示文字，不影響瀏覽器分頁標題。
st.set_page_config(page_title="資產管理", page_icon="💰")

# 放行後把組裝好的依賴容器存入 session，供各頁以同一容器取用，免每頁重組。
CONTAINER_SESSION_KEY = "container"


def _require_access() -> None:
    """登入守門：未登入顯示登入入口、非本人顯示拒絕，皆停止後續渲染。

    以 st.user 的登入狀態與 email 餵入純判定 evaluate_access；允許清單從 st.secrets 取得。
    任一未放行決策都 st.stop()，使非本人在登入後也不會觸發任何頁面渲染或資料讀取。

    st.user 在 [auth] 尚未設定時不帶 is_logged_in/email 屬性（存取會拋 AttributeError），
    以 getattr 取預設值，使「auth 未設定」退化為「未登入」而導向登入畫面，而非整頁崩潰。
    """
    is_logged_in = bool(getattr(st.user, "is_logged_in", False))
    decision = evaluate_access(
        is_logged_in=is_logged_in,
        email=getattr(st.user, "email", None) if is_logged_in else None,
        allowed_emails=bootstrap.allowed_emails(),
    )
    if decision.granted:
        return

    if decision.reason is AccessReason.NOT_LOGGED_IN:
        st.title("資產配置管理")
        st.write("請先以 Google 帳號登入以檢視財務資料。")
        st.button("使用 Google 登入", on_click=st.login)
    else:
        # 已登入但非允許本人：明確拒絕，不洩漏任何財務資料
        st.title("無權限")
        st.error("此帳號不在允許清單內，無法存取本工具的財務資料。")
        st.button("登出", on_click=st.logout)
    st.stop()


def main() -> None:
    """守門通過後組裝依賴並路由到當前頁面。"""
    _require_access()

    st.session_state[CONTAINER_SESSION_KEY] = bootstrap.get_resilient_container()

    with st.sidebar:
        st.caption(f"已登入：{st.user.email}")
        st.button("登出", on_click=st.logout)

    navigation = st.navigation(
        [
            st.Page("views/input.py", title="月度錄入", icon=":material/edit_note:"),
            st.Page("views/allocation.py", title="資產配置", icon=":material/donut_large:"),
            st.Page("views/returns.py", title="報酬率", icon=":material/trending_up:"),
            st.Page("views/protocol.py", title="行為協定", icon=":material/menu_book:"),
            st.Page("views/settings.py", title="設定", icon=":material/settings:"),
            st.Page("views/data_io.py", title="匯出入", icon=":material/import_export:"),
        ]
    )
    navigation.run()


main()
