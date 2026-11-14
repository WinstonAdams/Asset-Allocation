"""城市總覽的 Components v2 註冊與 wrapper（城市模組中唯一 import streamlit 者）。

元件於模組載入時註冊一次；js、css 傳內容字串（含換行才會被視為 inline）。
"""

# ==== 原生（標準庫） ====
from pathlib import Path

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
# 無

_ASSET_DIR = Path(__file__).parent
_COMPONENT_NAME = "city_overview"
_HTML = '<div class="city"><canvas class="city-canvas" role="img"></canvas></div>'

_COMPONENT = st.components.v2.component(
    _COMPONENT_NAME,
    html=_HTML,
    css=(_ASSET_DIR / "city.css").read_text(encoding="utf-8"),
    js=(_ASSET_DIR / "city.js").read_text(encoding="utf-8"),
)


def city_overview(*, payload: dict, key: str):
    """掛載城市元件。

    Args:
        payload: 傳給前端的資料（JSON 可序列化）。
        key: 元件的穩定 key；選取狀態存在 `session_state[key]`。

    Returns:
        元件結果，`.selected` 為前端以 setStateValue 回傳的選取 id。
    """
    return _COMPONENT(
        key=key,
        data=payload,
        width="stretch",
        height="content",
        on_selected_change=lambda: None,
    )
