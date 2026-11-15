"""城市總覽的 Components v2 註冊與 wrapper（城市模組中唯一 import streamlit 者）。

元件於模組載入時註冊一次；js、css 傳內容字串（含換行才會被視為 inline）。
幾何常數由 `geometry.geometry_json()` 序列化成 `const GEOM = ...;` 前置行，JS 只讀 `GEOM.*`。
"""

# ==== 原生（標準庫） ====
from pathlib import Path

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.city.geometry import geometry_json

_ASSET_DIR = Path(__file__).parent
_COMPONENT_NAME = "asset_lab_city"

# 版面骨架只放結構；所有文字（天氣、月份、圖例、提示）由 city.js 以 textContent 填入
COMPONENT_HTML = """
<div class="city" data-night="0">
  <div class="canvas-wrap" id="wrap">
    <canvas id="city" role="img"></canvas>
    <div class="weather" id="weather" data-sev="neutral">
      <span class="sev"></span>
      <div><div class="w-main" id="wMain"></div><div class="w-sub" id="wSub"></div></div>
    </div>
    <div class="mon" id="mon"></div>
    <div class="tip" id="tip" hidden></div>
  </div>
  <div class="legend" id="legend" hidden></div>
</div>
"""


def component_script() -> str:
    """送進元件的 JS：幾何常數前置行加上 city.js 原文。"""
    body = (_ASSET_DIR / "city.js").read_text(encoding="utf-8")
    return f"const GEOM = {geometry_json()};\n{body}"


_COMPONENT = st.components.v2.component(
    _COMPONENT_NAME,
    html=COMPONENT_HTML,
    css=(_ASSET_DIR / "city.css").read_text(encoding="utf-8"),
    js=component_script(),
)


def render_city(*, payload: dict[str, object], key: str) -> None:
    """掛載城市元件（寬度填滿、高度依內容）；只註冊選取變更的 no-op 回呼。

    Args:
        payload: 前後端契約字典（`payload.build_payload` 的結果，JSON 可序列化）。
        key: 元件的穩定 key；前端以 setStateValue 回報的選取 id 存在 `session_state[key]`。
    """
    _COMPONENT(
        key=key,
        data=payload,
        width="stretch",
        height="content",
        on_selected_change=lambda: None,
    )


def selected_in_session(*, key: str) -> object:
    """讀元件上一次回報的選取值；尚無時為 None。原樣回傳，由 payload.resolve_selection 驗證。"""
    state = st.session_state.get(key)
    if state is None:
        return None
    if isinstance(state, dict):
        return state.get("selected")
    return getattr(state, "selected", None)


# 總覽頁整合完成前的過渡別名，頁面改用 render_city 後移除
city_overview = render_city
