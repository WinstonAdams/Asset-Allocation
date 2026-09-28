"""金額輸入元件與全站放大樣式（BR-9/BR-10）。

金額欄改用 `st.text_input` 顯示整數千分位（`core/utils.format_amount`／`parse_amount`
負責純格式化與解析），本模組把「初值格式化＋on_change 正規化」包成一個可重用元件，
並提供全站樣式注入函式：靠 Streamlit keyed container 產生的 `st-key-*` class 精準放大
金額欄，不影響同頁其他非金額 `text_input`（如項目名稱）。

本模組會 import streamlit，是 `src/asset_lab/` 下允許直接操作 Streamlit runtime 的 UI
元件模組（比照 `bootstrap.py`）；Service/Repository 仍不 import streamlit。
"""

# ==== 原生（標準庫） ====
from collections.abc import Callable

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.core.utils import format_amount, parse_amount

# 外層 container key 前綴：所有金額欄的外層 container key 皆以此開頭，讓
# inject_amount_input_style 的 CSS 選擇器可以用同一個前綴精準命中，不必逐一列出
# 每個金額欄各自的 key。
_CONTAINER_KEY_PREFIX = "amount-input-"

# 放大後的字級與高度：明顯大於 Streamlit 預設輸入框，讓金額欄清楚可辨（BR-10）。
_FONT_SIZE = "1.25rem"
_HEIGHT = "3rem"


def amount_input(
    label: str,
    *,
    key: str,
    value: float | None = 0.0,
    on_change: Callable[..., None] | None = None,
    kwargs: dict | None = None,
) -> str:
    """千分位金額輸入框：外層包一個有 key 的 container，供全站放大樣式選取。

    初值以 `format_amount` 格式化成千分位字串，只在該 key 尚未存在於
    `session_state` 時播種（用 `setdefault`，避免「value 參數與 Session State API
    同時設定」的警告；之後每次 rerun 沿用 session_state 內的值，符合 Streamlit
    keyed widget 的既有語意）。

    自帶一個 `on_change`：先嘗試把 `session_state[key]` 正規化成千分位格式（能解析
    才改寫，讓欄位離開焦點後所見即所存；解析失敗就保留使用者原始輸入，留給存檔時
    的 `parse_amount` 報錯，不在這裡動使用者還沒改完的文字），再呼叫呼叫端傳入的
    `on_change(**kwargs)`，讓既有的同步回呼（如活存/定存成本帶入市值）可以接續。

    Args:
        label: 欄位標籤。
        key: widget key；同時作為外層 container key 的一部分。
        value: 初始數值；`None` 顯示空字串。僅在該 key 於 session_state 尚不存在時生效。
        on_change: 正規化完成後才呼叫的呼叫端回呼。
        kwargs: 傳給 on_change 的關鍵字參數。

    Returns:
        使用者目前輸入的原始字串；數值解析交由呼叫端在存檔時呼叫 `parse_amount`。
    """
    st.session_state.setdefault(key, format_amount(value))

    def _handle_change() -> None:
        _normalize_session_value(key)
        if on_change is not None:
            on_change(**(kwargs or {}))

    with st.container(key=f"{_CONTAINER_KEY_PREFIX}{key}"):
        st.text_input(label, key=key, on_change=_handle_change)

    return st.session_state[key]


def _normalize_session_value(key: str) -> None:
    """把 `session_state[key]` 的文字正規化成千分位格式；解析失敗保留原字串。

    Args:
        key: 目標欄位的 session_state key。
    """
    try:
        parsed = parse_amount(st.session_state[key], field_label=key)
    except DataValidationError:
        return
    st.session_state[key] = format_amount(parsed)


def inject_amount_input_style() -> None:
    """注入全站樣式，放大金額輸入框的字級與高度，且只套用於金額欄（BR-10）。

    以 `[class*="st-key-<前綴>"] input` 選中 `amount_input` 外層 container 底下的
    `<input>`；只有帶這個前綴的 container 會命中，同頁其他沒有此前綴的 `text_input`
    （如項目名稱）不受影響。用 `st.html` 注入純 style 內容，不佔版面。

    需在 app.py 的登入守門通過後、`st.navigation` 執行前呼叫一次，所有頁面才會生效
    （AppTest 單獨驅動 `views/*.py` 時未經過 app.py，不會套用此樣式；實際放大後的
    視覺效果留待 2-Z 啟動驗證階段人工確認）。
    """
    st.html(
        f'<style>[class*="st-key-{_CONTAINER_KEY_PREFIX}"] input '
        f"{{ font-size: {_FONT_SIZE}; height: {_HEIGHT}; }}</style>"
    )
