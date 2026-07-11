"""回歸測試：頁面資料夾不得觸發 Streamlit 自動多頁探索（認證繞過修正）。

背景：早期頁面檔曾放在字面命名為 `pages/` 的資料夾。`pages/` 是 Streamlit 的保留資料夾
名——只要它與入口腳本（`app.py`）同層存在，框架就會啟動「檔案系統自動多頁」模式，把每個
子頁獨立註冊為可直接以 URL 存取的頁面（如 `/allocation`），完全繞過 `app.py`
`_require_access()` 的登入守門，且側邊欄改用檔名而非 `st.Page(title=...)` 設定的中文標題。

修正做法：頁面檔改放非保留名 `views/`，導覽僅由 `app.py` 內的 `st.navigation`
程式化註冊。本檔驗證觸發條件本身不再成立，防止此認證繞過再次回歸：

1. 專案根目錄不存在字面上的 `pages/` 資料夾（觸發條件的必要前提）。
2. Streamlit 判定「是否啟用自動多頁」的真實邏輯
   （`streamlit.runtime.pages_manager.PagesManager.uses_pages_directory`），
   以本專案入口 `app.py` 現場重算，結果必須為 False。
"""

# ==== 原生（標準庫） ====
from pathlib import Path

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
# 無

APP_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.scenario("SC-040")
def test_no_reserved_pages_directory_beside_entrypoint():
    # pages/ 是 Streamlit 保留資料夾名；存在即觸發自動多頁探索，前提本身不可成立
    assert not (APP_DIR / "pages").exists()


@pytest.mark.scenario("SC-040")
def test_views_directory_holds_the_page_files_instead():
    # 頁面檔改放非保留名 views/，內容維持齊全（不因改名遺漏）
    expected = {"input.py", "allocation.py", "returns.py", "settings.py", "data_io.py"}
    actual = {p.name for p in (APP_DIR / "views").glob("*.py")}
    assert expected <= actual


@pytest.mark.scenario("SC-040")
def test_streamlit_pages_manager_does_not_detect_auto_discovery():
    from streamlit.runtime.pages_manager import PagesManager

    # 此旗標於行程內第一次建立 PagesManager 時計算一次並快取於類別層級；
    # 重置後以本專案真實入口路徑重新現場計算，才是對「當下專案結構」的有效驗證。
    PagesManager.uses_pages_directory = None
    PagesManager(main_script_path=str(APP_DIR / "app.py"))
    assert PagesManager.uses_pages_directory is False
