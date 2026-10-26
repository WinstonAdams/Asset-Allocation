"""全站錯誤兜底的 runtime 黏合：未預期錯誤只顯示通用訊息，細節寫入 log。

領域例外（AssetLabError）的訊息本來就是給使用者看的，原樣顯示；其他未預期例外在雲端
（錯誤細節開關關閉）只顯示通用訊息，開關開啟（本機除錯）時原樣往上拋，交給 Streamlit
以完整錯誤畫面顯示。st.stop／st.rerun 的控制例外（BaseException）一律不攔截。
"""

# ==== 原生（標準庫） ====
import logging
from collections.abc import Iterator
from contextlib import contextmanager

# ==== 第三方套件 ====
import streamlit as st
from streamlit.errors import FragmentHandledException

# ==== 專案內部 ====
from asset_lab.core.constants import ERROR_DETAILS
from asset_lab.core.exceptions import AssetLabError

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR_MESSAGE = "發生未預期錯誤，請稍後再試"


def error_details_enabled() -> bool:
    """以 Streamlit 的 client.showErrorDetails 設定值判斷是否顯示完整錯誤。

    設定值由 app.py 依專案環境變數每次執行時寫入，是唯一依據，本模組不讀環境變數。

    Returns:
        設定值為完整模式時回 True。
    """
    return st.get_option("client.showErrorDetails") == ERROR_DETAILS.SHOW


@contextmanager
def error_boundary(*, context: str) -> Iterator[None]:
    """最後防線：依例外類別決定顯示友善訊息、通用訊息或原樣往上拋。

    Args:
        context: 發生位置的標籤，帶進 log 以便追查。

    Yields:
        None。
    """
    try:
        yield
    except FragmentHandledException:
        # Streamlit 已顯示並記錄過，不重複處理
        raise
    except AssetLabError as error:
        logger.exception("領域錯誤 context=%s", context)
        st.error(str(error))
    except Exception:
        logger.exception("未預期錯誤 context=%s", context)
        if error_details_enabled():
            raise
        st.error(UNEXPECTED_ERROR_MESSAGE)
