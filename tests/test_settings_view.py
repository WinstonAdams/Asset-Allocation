"""設定頁呈現層與持有項目主檔編輯行為的測試。

本檔含兩類測試：
①純呈現層調整（無新業務語義，不掛 SC marker）——「性質」selectbox 改用 format_func
顯示中文「資產/負債」，內部值仍為 HOLDING_KIND.ASSET="asset"/LIABILITY="liability"；
初始市值/初始成本 number_input 改用 format="%.0f" 不顯示小數，內部值仍為 float；目標
比重 number_input 的 label 加註「（%）」。這些皆不改變下層 Model/Service/Repository
的介面或值。既有項目的編輯入口（改名/改分類/改初始值後委派 HoldingRepository.
update_holding）亦屬此類——holding_id 穩定與改分類非時間版本化的業務正確性已由
test_holding_master.py 的 SC-003/SC-004 覆蓋，本檔只驗證 UI 到 Repository 呼叫邊界
的資料傳遞，不重掛 marker。

②SC-051（活存/定存分類初始成本預設帶入初始市值）——新增或編輯資產項目時，只要當下
分類為活存/定存，初始成本欄位即自動帶入與初始市值相同的數字，使用者仍可手動覆蓋。

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
from asset_lab.models.holding import HoldingModel
from asset_lab.services.protocol_service import ProtocolService


class _StubHoldingRepo:
    """主檔替身：可注入既有項目清單；update_holding 呼叫會被記錄供斷言。"""

    def __init__(self, holdings: list[HoldingModel] | None = None):
        self._holdings = list(holdings) if holdings else []
        self.updated: list[HoldingModel] = []

    def list_holdings(self):
        return self._holdings

    def add_holding(self, *, holding):
        pass

    def update_holding(self, *, holding):
        self.updated.append(holding)


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


def _run_app(*, holding_repo: _StubHoldingRepo | None = None) -> AppTest:
    """以替身容器跑 views/settings.py，回傳已 run() 完成的 AppTest。"""
    container = SimpleNamespace(
        holding_repo=holding_repo or _StubHoldingRepo(),
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


class TestNewHoldingCashLikeCategoryCostDefaultsToMarketValue:
    """SC-051（新增流程）：分類為活存/定存時，初始成本預設帶入初始市值，且可再手動覆蓋。"""

    @pytest.mark.scenario("SC-051")
    def test_sc043_demand_deposit_cost_follows_market_value(self):
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        at.number_input(key="new_market_value").set_value(123456.0).run()
        cost = at.number_input(key="new_cost")
        assert cost.value == 123456.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_time_deposit_cost_follows_market_value(self):
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TIME_DEPOSIT).run()
        at.number_input(key="new_market_value").set_value(50000.0).run()
        cost = at.number_input(key="new_cost")
        assert cost.value == 50000.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_user_can_still_manually_override_cost(self):
        # 自動帶入後使用者再手動改成別的值：改後的值須維持，不被覆蓋回市值
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        at.number_input(key="new_market_value").set_value(123456.0).run()
        at.number_input(key="new_cost").set_value(999.0).run()
        cost = at.number_input(key="new_cost")
        assert cost.value == 999.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_non_cash_category_cost_not_auto_filled(self):
        # 其他分類（股票/ETF 等）行為不變：改市值不影響成本欄位既有值
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TW_STOCK).run()
        at.number_input(key="new_market_value").set_value(500000.0).run()
        cost = at.number_input(key="new_cost")
        assert cost.value == 0.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_switching_from_cash_to_other_category_stops_auto_fill(self):
        # 從活存切回股票分類後，成本欄位不再隨市值自動帶入
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        at.number_input(key="new_market_value").set_value(123456.0).run()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TW_STOCK).run()
        at.number_input(key="new_market_value").set_value(777.0).run()
        cost = at.number_input(key="new_cost")
        assert cost.value == 123456.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_switching_into_cash_category_syncs_existing_market_value(self):
        # 已在其他分類填好市值，才改選活存/定存：切換當下即以既有市值覆蓋成本欄位
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TW_STOCK).run()
        at.number_input(key="new_market_value").set_value(500000.0).run()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        cost = at.number_input(key="new_cost")
        assert cost.value == 500000.0


class TestEditExistingHoldingWiresToRepository:
    """既有項目編輯入口的純呈現/委派層測試（不掛 SC marker）。

    改名/改分類不影響 holding_id、分類非時間版本化等業務正確性已由
    test_holding_master.py 的 SC-003/SC-004（直接測 Repository）覆蓋；本處只驗證
    設定頁確實提供編輯入口，且儲存時把使用者輸入正確組成 HoldingModel 委派
    update_holding，資料傳遞沒有被 UI 改版破壞。
    """

    def test_editing_name_and_saving_calls_update_holding_with_same_id(self):
        holding = HoldingModel(
            holding_id=5,
            name="台積電",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_market_value=500000.0,
            initial_cost=300000.0,
        )
        repo = _StubHoldingRepo(holdings=[holding])
        at = _run_app(holding_repo=repo)
        at.text_input(key="edit_5_name").set_value("TSMC").run()
        save_button = next(b for b in at.button if b.key == "edit_5_save")
        save_button.click().run()
        assert len(repo.updated) == 1
        updated = repo.updated[0]
        assert updated.holding_id == 5
        assert updated.name == "TSMC"
        # 未變動的欄位（分類/市值/成本）原樣保留，不因改名而被清空或改變
        assert updated.category == ASSET_CATEGORIES.TW_STOCK
        assert updated.initial_market_value == 500000.0
        assert updated.initial_cost == 300000.0

    def test_editing_category_and_saving_persists_new_category(self):
        holding = HoldingModel(
            holding_id=6,
            name="0050",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_market_value=200000.0,
            initial_cost=200000.0,
        )
        repo = _StubHoldingRepo(holdings=[holding])
        at = _run_app(holding_repo=repo)
        at.selectbox(key="edit_6_cat").select(ASSET_CATEGORIES.US_STOCK).run()
        save_button = next(b for b in at.button if b.key == "edit_6_save")
        save_button.click().run()
        assert repo.updated[0].holding_id == 6
        assert repo.updated[0].category == ASSET_CATEGORIES.US_STOCK

    def test_liability_edit_only_shows_name_field_and_saves_without_category(self):
        # 負債編輯區塊不顯示分類/初始市值/初始成本欄位（比照新增流程的性質分支）
        holding = HoldingModel(
            holding_id=7,
            name="房貸",
            kind=HOLDING_KIND.LIABILITY,
            category=None,
            initial_market_value=None,
            initial_cost=None,
        )
        repo = _StubHoldingRepo(holdings=[holding])
        at = _run_app(holding_repo=repo)
        assert not at.exception
        with pytest.raises(KeyError):
            at.selectbox(key="edit_7_cat")
        save_button = next(b for b in at.button if b.key == "edit_7_save")
        save_button.click().run()
        assert repo.updated[0].category is None
        assert repo.updated[0].initial_market_value is None

    def test_multiple_holdings_have_independent_edit_widget_keys(self):
        # 多個既有項目同時列出，各自編輯欄位的 session_state key 不互相干擾
        holdings = [
            HoldingModel(
                holding_id=1,
                name="台積電",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TW_STOCK,
                initial_market_value=500000.0,
                initial_cost=300000.0,
            ),
            HoldingModel(
                holding_id=2,
                name="房貸",
                kind=HOLDING_KIND.LIABILITY,
                category=None,
                initial_market_value=None,
                initial_cost=None,
            ),
        ]
        at = _run_app(holding_repo=_StubHoldingRepo(holdings=holdings))
        assert not at.exception
        assert at.text_input(key="edit_1_name").value == "台積電"
        assert at.text_input(key="edit_2_name").value == "房貸"


class TestEditExistingHoldingCashLikeCategoryCostDefaultsToMarketValue:
    """SC-051（編輯流程）：既有項目改分類為活存/定存，或改市值時，成本比照新增流程同步。"""

    @pytest.mark.scenario("SC-051")
    def test_sc043_edit_changing_category_to_demand_deposit_then_market_value_syncs_cost(self):
        holding = HoldingModel(
            holding_id=1,
            name="台積電",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_market_value=500000.0,
            initial_cost=300000.0,
        )
        at = _run_app(holding_repo=_StubHoldingRepo(holdings=[holding]))
        at.selectbox(key="edit_1_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        at.number_input(key="edit_1_market_value").set_value(88000.0).run()
        cost = at.number_input(key="edit_1_cost")
        assert cost.value == 88000.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_edit_already_cash_category_cost_follows_market_value_change(self):
        # 編輯時分類本來就是活存，只改市值：成本仍應同步跟隨
        holding = HoldingModel(
            holding_id=2,
            name="活存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.DEMAND_DEPOSIT,
            initial_market_value=100000.0,
            initial_cost=100000.0,
        )
        at = _run_app(holding_repo=_StubHoldingRepo(holdings=[holding]))
        at.number_input(key="edit_2_market_value").set_value(150000.0).run()
        cost = at.number_input(key="edit_2_cost")
        assert cost.value == 150000.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_edit_user_can_still_manually_override_cost(self):
        holding = HoldingModel(
            holding_id=3,
            name="定存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            initial_market_value=200000.0,
            initial_cost=200000.0,
        )
        at = _run_app(holding_repo=_StubHoldingRepo(holdings=[holding]))
        at.number_input(key="edit_3_market_value").set_value(250000.0).run()
        at.number_input(key="edit_3_cost").set_value(210000.0).run()
        cost = at.number_input(key="edit_3_cost")
        assert cost.value == 210000.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_edit_non_cash_category_cost_not_auto_filled(self):
        holding = HoldingModel(
            holding_id=4,
            name="台積電",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_market_value=500000.0,
            initial_cost=300000.0,
        )
        at = _run_app(holding_repo=_StubHoldingRepo(holdings=[holding]))
        at.number_input(key="edit_4_market_value").set_value(600000.0).run()
        cost = at.number_input(key="edit_4_cost")
        assert cost.value == 300000.0

    @pytest.mark.scenario("SC-051")
    def test_sc043_edit_save_persists_auto_filled_cost_when_not_overridden(self):
        # 自動帶入後未手動覆蓋就儲存：實際寫入的 initial_cost 為帶入值（非原始值）
        holding = HoldingModel(
            holding_id=8,
            name="活存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.DEMAND_DEPOSIT,
            initial_market_value=100000.0,
            initial_cost=100000.0,
        )
        repo = _StubHoldingRepo(holdings=[holding])
        at = _run_app(holding_repo=repo)
        at.number_input(key="edit_8_market_value").set_value(120000.0).run()
        save_button = next(b for b in at.button if b.key == "edit_8_save")
        save_button.click().run()
        assert repo.updated[0].initial_market_value == 120000.0
        assert repo.updated[0].initial_cost == 120000.0
