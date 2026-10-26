"""全站錯誤兜底的 runtime 黏合：未預期錯誤只顯示通用訊息，細節寫入 log。

領域例外（AssetLabError）的訊息本來就是給使用者看的，原樣顯示；其他未預期例外在雲端
（錯誤細節開關關閉）只顯示通用訊息，開關開啟（本機除錯）時原樣往上拋，交給 Streamlit
以完整錯誤畫面顯示。st.stop／st.rerun 的控制例外（BaseException）一律不攔截。
"""

# ==== 原生（標準庫） ====
import functools
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

# ==== 第三方套件 ====
import streamlit as st
from streamlit.errors import FragmentHandledException

# ==== 專案內部 ====
from asset_lab.core.constants import ERROR_DETAILS
from asset_lab.core.exceptions import AssetLabError

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR_MESSAGE = "發生未預期錯誤，請稍後再試"
CALLBACK_ERROR_SESSION_KEY = "callback_error_message"

F = TypeVar("F", bound=Callable)


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


def guarded_callback(*, context: str) -> Callable[[F], F]:
    """widget callback 用：分類同 error_boundary，但不輸出元素，訊息暫存到 session_state。

    callback 在腳本主體之前執行，直接輸出的元素位置不固定；改暫存訊息，由頁面在標題下方
    呼叫 show_callback_error 顯示，頁面本身照常渲染。

    Args:
        context: 發生位置的標籤，帶進 log 以便追查。

    Returns:
        裝飾器。
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except AssetLabError as error:
                logger.exception("領域錯誤 context=%s", context)
                st.session_state[CALLBACK_ERROR_SESSION_KEY] = str(error)
            except Exception:
                logger.exception("未預期錯誤 context=%s", context)
                if error_details_enabled():
                    raise
                st.session_state[CALLBACK_ERROR_SESSION_KEY] = UNEXPECTED_ERROR_MESSAGE

        return wrapper  # type: ignore[return-value]

    return decorator


def show_callback_error() -> None:
    """取出並清掉 callback 暫存的錯誤訊息，有的話以紅字顯示（只顯示一次）。"""
    message = st.session_state.pop(CALLBACK_ERROR_SESSION_KEY, None)
    if message:
        st.error(message)
