"""amount_widget 模組：金額輸入元件與全站放大樣式的測試（SC-083）。

以 `AppTest.from_string` 直接驅動 `amount_widget` 的兩個 public 函式，不需要真正的
頁面整合（元件是後續 views/input.py、views/settings.py 共同依賴的基礎設施，見
task t06 切片理由）。

分成三類：
① SC-083（本檔正式對映的 Scenario）——`inject_amount_input_style()` 注入的 CSS
   選擇器與 `amount_input()` 外層 container 的 key 前綴一致，且樣式確實放大字級與
   高度；同頁沒有套用 `amount_input` 的一般 `text_input`（如項目名稱）不會被包進
   帶該前綴的 container，因此不會被選中。實際放大後的視覺效果需經 app.py 注入才會
   套用（AppTest 單獨驅動本模組不經過 app.py），留待 2-Z 啟動驗證階段人工確認。
② 千分位顯示與正規化的業務行為（BR-9，已由 SC-081 描述「輸入後欄位離開焦點即正規化
   顯示千分位」）——這裡驗證的是同一條業務規則在 widget 層（實際 Streamlit 欄位
   的初值與 on_change）的落實，掛回 SC-081，不是新的業務邊界；其中一個案例額外用
   呼叫端 on_change 回呼當觀察窗口，確認正規化後的值有正確傳遞出去（仍在驗證
   SC-081 的正規化結果，串接呼叫端回呼本身是 AD-7 的技術契約，非另立業務邊界）。
③ 解析失敗時原樣保留文字、不崩潰（掛回 SC-082）——SC-082 要求「無法解析或留空的
   輸入必須在存檔時被擋下、不落庫」；這個保證成立的前提是 widget 的 on_change 不能
   在存檔前就把使用者還沒改完（或無效）的文字悄悄改掉或讓程式崩潰，否則存檔時就
   看不到原始的無效輸入可供 `parse_amount` 拒絕。本檔驗證的正是這個前提，不是重複
   t05（tests/test_core_utils.py）已覆蓋的「存檔時拒絕並提示」本身。
"""

# ==== 原生（標準庫） ====
import re
import textwrap

# ==== 第三方套件 ====
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
# 無（透過 AppTest 執行的腳本字串內部才 import asset_lab.amount_widget）

_SINGLE_FIELD_SCRIPT = textwrap.dedent(
    """
    from asset_lab.amount_widget import amount_input

    amount_input("現值", key="amt_a", value={value!r})
    """
)


def _run_single_field(value: float | None = 0) -> AppTest:
    """驅動一個 amount_input 欄位（key="amt_a"）並回傳已執行的 AppTest。"""
    return AppTest.from_string(_SINGLE_FIELD_SCRIPT.format(value=value)).run()


class TestAmountInputInitialValueFormatting:
    """amount_input 首次渲染即以整數千分位顯示初值（SC-081 的顯示規則落實於 widget 層）。"""

    @pytest.mark.scenario("SC-081")
    def test_sc081_initial_value_shows_thousands_separator(self):
        at = _run_single_field(value=1234567)
        assert at.text_input(key="amt_a").value == "1,234,567"

    @pytest.mark.scenario("SC-081")
    def test_sc081_initial_negative_value_shows_minus_sign(self):
        at = _run_single_field(value=-50000)
        assert at.text_input(key="amt_a").value == "-50,000"

    @pytest.mark.scenario("SC-081")
    def test_sc081_initial_none_value_shows_empty_string(self):
        at = _run_single_field(value=None)
        assert at.text_input(key="amt_a").value == ""


class TestAmountInputOnChangeNormalizesOnBlur:
    """使用者輸入後欄位離開焦點（on_change），正規化顯示為整數千分位（SC-081）。"""

    @pytest.mark.scenario("SC-081")
    def test_sc081_plain_number_normalizes_to_thousands(self):
        at = _run_single_field(value=0)
        at.text_input(key="amt_a").set_value("1234567").run()
        assert at.text_input(key="amt_a").value == "1,234,567"

    @pytest.mark.scenario("SC-081")
    def test_sc081_already_grouped_input_stays_the_same(self):
        at = _run_single_field(value=0)
        at.text_input(key="amt_a").set_value("1,234,567").run()
        assert at.text_input(key="amt_a").value == "1,234,567"

    @pytest.mark.scenario("SC-081")
    def test_sc081_negative_input_normalizes_with_minus_sign(self):
        at = _run_single_field(value=0)
        at.text_input(key="amt_a").set_value("-50000").run()
        assert at.text_input(key="amt_a").value == "-50,000"

    @pytest.mark.scenario("SC-081")
    def test_sc081_decimal_input_rounds_away_from_zero(self):
        # 邊界：帶小數四捨五入（遠離零）成整數後才加千分位
        at = _run_single_field(value=0)
        at.text_input(key="amt_a").set_value("1234567.6").run()
        assert at.text_input(key="amt_a").value == "1,234,568"

    @pytest.mark.scenario("SC-081")
    def test_sc081_fullwidth_digits_and_comma_normalize(self):
        # 邊界：全形數字／全形逗號（中文輸入法）等價於半形輸入
        at = _run_single_field(value=0)
        at.text_input(key="amt_a").set_value("１，２３４").run()
        assert at.text_input(key="amt_a").value == "1,234"

    @pytest.mark.scenario("SC-081")
    def test_sc081_normalized_value_is_delivered_to_caller_on_change(self):
        # 以呼叫端 on_change 當觀察窗口：正規化後的字串（而非原始輸入）才是往下傳遞
        # 的值，驗證的仍是 SC-081 的正規化結果；呼叫順序／參數傳遞本身是 AD-7 的
        # 技術契約，供 t09 串接既有同步回呼（如 SC-051）使用。
        script = textwrap.dedent(
            """
            import streamlit as st
            from asset_lab.amount_widget import amount_input

            def _sync(*, target_key):
                st.session_state[target_key] = "synced:" + st.session_state["amt_a"]

            amount_input(
                "現值", key="amt_a", value=0,
                on_change=_sync, kwargs={"target_key": "other"},
            )
            st.session_state.setdefault("other", "")
            st.text("other=" + st.session_state["other"])
            """
        )
        at = AppTest.from_string(script).run()
        at.text_input(key="amt_a").set_value("1234567").run()
        assert at.text[0].value == "other=synced:1,234,567"


class TestAmountInputUnparsableInputStaysAvailableForSaveTimeRejection:
    """解析失敗或清空時原樣保留文字、不崩潰，掛回 SC-082。

    SC-082 的保證是「無法解析或留空的輸入在存檔時被擋下、不落庫」；這裡驗證的是
    這個保證在 widget 層成立的必要前提——on_change 不會把使用者還沒改完（或無效）
    的文字悄悄改掉或讓程式崩潰，讓存檔時 `parse_amount` 仍能看到原始文字並正確拒絕
    （存檔時的拒絕判定與錯誤提示本身已在 t05 的 tests/test_core_utils.py 覆蓋，
    不在本檔重複）。
    """

    @pytest.mark.scenario("SC-082")
    def test_sc082_non_standard_grouping_left_unchanged_for_later_rejection(self):
        at = _run_single_field(value=0)
        at.text_input(key="amt_a").set_value("1,00,000").run()
        assert not at.exception
        assert at.text_input(key="amt_a").value == "1,00,000"

    @pytest.mark.scenario("SC-082")
    def test_sc082_cleared_to_empty_string_left_unchanged_for_later_rejection(self):
        at = _run_single_field(value=100)
        at.text_input(key="amt_a").set_value("").run()
        assert not at.exception
        assert at.text_input(key="amt_a").value == ""


_STYLE_SCRIPT = textwrap.dedent(
    """
    import streamlit as st
    from asset_lab.amount_widget import amount_input, inject_amount_input_style

    amount_input("現值", key="amt_a", value=1234567)
    st.text_input("項目名稱", key="holding_name")
    inject_amount_input_style()
    """
)


def _style_body(at: AppTest) -> str:
    """取出 inject_amount_input_style() 注入的 <style> 原始字串。"""
    return at.get("html")[0].proto.body


class TestInjectAmountInputStyleTargetsAmountFieldsOnly:
    """SC-083：全站放大樣式只命中 amount_input 產生的欄位，不影響其他 text_input。"""

    @pytest.mark.scenario("SC-083")
    def test_sc083_selector_prefix_matches_amount_input_container_key(self):
        at = AppTest.from_string(_STYLE_SCRIPT).run()
        style = _style_body(at)

        match = re.search(r'st-key-([\w-]+)"', style)
        assert match, f"樣式字串應含 st-key-<前綴> 選擇器，實際內容：{style!r}"
        prefix = match.group(1)

        amount_container = at.main.children[0]
        assert prefix in amount_container.proto.id, (
            "amount_input 外層 container 的 key 應以樣式選擇器引用的前綴開頭，"
            "否則放大樣式不會命中金額欄"
        )

    @pytest.mark.scenario("SC-083")
    def test_sc083_style_declares_noticeably_larger_font_and_height(self):
        at = AppTest.from_string(_STYLE_SCRIPT).run()
        style = _style_body(at)

        font_size_match = re.search(r"font-size:\s*([\d.]+)rem", style)
        height_match = re.search(r"height:\s*([\d.]+)rem", style)
        assert font_size_match, f"樣式應宣告 font-size，實際內容：{style!r}"
        assert height_match, f"樣式應宣告 height，實際內容：{style!r}"
        # Streamlit 預設輸入框字級約 1rem；明顯放大要求嚴格大於預設值。
        assert float(font_size_match.group(1)) > 1.0
        assert float(height_match.group(1)) > 1.0

    @pytest.mark.scenario("SC-083")
    def test_sc083_non_amount_text_input_is_not_wrapped_by_the_special_container(self):
        # 「項目名稱」欄不經 amount_input，結構上不會被包進帶樣式前綴的 container，
        # 因此不會被 CSS 選擇器命中，維持原本大小（SC-083 的 AND 子句）。
        at = AppTest.from_string(_STYLE_SCRIPT).run()
        style = _style_body(at)
        match = re.search(r'st-key-([\w-]+)"', style)
        prefix = match.group(1)

        name_input = at.text_input(key="holding_name")
        # AppTest 的 ElementTree 沒有公開的「父節點」反查 API；改以正向列舉
        # main 下每個 Block 的子孫，確認 holding_name 只出現在不帶樣式前綴的節點裡。
        wrapped_keys = _keys_wrapped_by_prefixed_container(at, prefix)
        assert name_input.key not in wrapped_keys
        assert "amt_a" in wrapped_keys


def _keys_wrapped_by_prefixed_container(at: AppTest, prefix: str) -> set[str]:
    """回傳所有巢狀在「id 含 prefix 的 Block」底下的 widget key 集合。"""
    wrapped: set[str] = set()

    def walk(node, inside_prefixed: bool) -> None:
        node_id = getattr(getattr(node, "proto", None), "id", "") or ""
        now_inside = inside_prefixed or (prefix in node_id)
        key = getattr(node, "key", None)
        if now_inside and key:
            wrapped.add(key)
        for child in (getattr(node, "children", None) or {}).values():
            walk(child, now_inside)

    walk(at.main, False)
    return wrapped
