"""設定頁三處純呈現層調整的行為測試（純 UI 機制，無新業務語義，不掛 SC marker）。

背景：views/settings.py 三處呈現調整——①「性質」selectbox 改用 format_func 顯示中文
「資產/負債」，內部值仍為 HOLDING_KIND.ASSET="asset"/LIABILITY="liability"（既有的
`if kind == HOLDING_KIND.ASSET` 業務分支與資料庫既有值不受影響）；②初始市值/初始成本
number_input 改用 format="%.0f" 不顯示小數，內部值仍為 float；③目標比重 number_input
的 label 加註「（%）」（st.number_input 的 format 需能被還原成合法 float，無法直接附加
"%" 文字後綴，因此以 label 呈現單位，非 format 呈現）。三處皆不改變下層 Model/Service/
Repository 的介面或值，因此無新增 SC，本檔只驗證呈現層本身。

比照 test_input_view.py 的做法：以 AppTest 直接載入 views/settings.py，改以替身容器
（含最小可用替身）注入 session_state["container"]，脫離真實 Turso 依賴。
"""

# ==== 原生（標準庫） ====
from types import SimpleNamespace

# ==== 第三方套件 ====
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND
from asset_lab.services.protocol_service import ProtocolService


class _StubHoldingRepo:
    """主檔替身：無既有項目，只需支撐「新增項目」表單渲染。"""

    def list_holdings(self):
        return []

    def add_holding(self, *, holding):
        pass


class _StubTargetRepo:
    """目標比重替身：無既有設定，供 _render_targets 與 _render_drift 讀取。"""

    def read_targets(self):
        return []

    def upsert_target(self, *, target):
        pass


class _StubRecordRepo:
    """記錄層替身：回報「尚無月度紀錄」，讓 _render_drift 提早結束，不需模擬 AllocationService。"""

    def latest_year_month(self):
        return None


class _StubProtocolThresholdRepo:
    """門檻替身：無既有保存值，ProtocolService 會補上預設值。"""

    def read_thresholds(self):
        return []


def _run_app() -> AppTest:
    """以替身容器跑 views/settings.py，回傳已 run() 完成的 AppTest。"""
    container = SimpleNamespace(
        holding_repo=_StubHoldingRepo(),
        target_repo=_StubTargetRepo(),
        record_repo=_StubRecordRepo(),
        allocation_service=None,
        protocol_threshold_repo=_StubProtocolThresholdRepo(),
        protocol_service=ProtocolService(),
    )
    at = AppTest.from_file("views/settings.py")
    at.session_state["container"] = container
    at.run()
    return at


class TestHoldingKindChineseLabel:
    """「性質」selectbox 顯示中文，選取後取得的內部值仍為 HOLDING_KIND 的英文字串。"""

    def test_options_show_chinese_labels(self):
        at = _run_app()
        assert not at.exception
        kind_select = at.selectbox(key="new_kind")
        assert kind_select.options == ["資產", "負債"]

    def test_default_value_is_internal_asset_string(self):
        at = _run_app()
        kind_select = at.selectbox(key="new_kind")
        assert kind_select.value == HOLDING_KIND.ASSET

    def test_selecting_liability_label_keeps_internal_value_and_switches_branch(self):
        # 選「負債」後：內部值仍是 HOLDING_KIND.LIABILITY，且既有的資產專屬欄位
        # （分類/初始市值/初始成本）分支正確跟著內部值切換（不受中文顯示影響）。
        at = _run_app()
        at.selectbox(key="new_kind").select(HOLDING_KIND.LIABILITY).run()
        kind_select = at.selectbox(key="new_kind")
        assert kind_select.value == HOLDING_KIND.LIABILITY
        assert kind_select.options[kind_select.index] == "負債"
        with pytest.raises(KeyError):
            at.number_input(key="new_market_value")
        with pytest.raises(KeyError):
            at.number_input(key="new_cost")


class TestInitialValueCostNoDecimal:
    """初始市值/初始成本輸入框不顯示小數，內部值仍為 float。"""

    def test_market_value_and_cost_use_integer_display_format(self):
        at = _run_app()
        market_value = at.number_input(key="new_market_value")
        cost = at.number_input(key="new_cost")
        assert market_value.proto.format == "%.0f"
        assert cost.proto.format == "%.0f"

    def test_market_value_and_cost_internal_value_still_float(self):
        at = _run_app()
        market_value = at.number_input(key="new_market_value")
        cost = at.number_input(key="new_cost")
        assert isinstance(market_value.value, float)
        assert isinstance(cost.value, float)


class TestTargetWeightPercentLabel:
    """目標比重輸入框的 label 加註「（%）」，輸入值本身不受影響。"""

    def test_target_weight_labels_show_percent_suffix(self):
        at = _run_app()
        for category in ASSET_CATEGORIES.ALL:
            weight_input = at.number_input(key=f"target_{category}")
            assert weight_input.label == f"{category}（%）"

    def test_target_weight_value_unaffected_by_label_change(self):
        at = _run_app()
        for category in ASSET_CATEGORIES.ALL:
            weight_input = at.number_input(key=f"target_{category}")
            assert weight_input.value == 0.0
