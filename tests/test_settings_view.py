"""設定頁呈現層與持有項目主檔編輯行為的測試。

本檔含三類測試：
①純呈現層調整（無新業務語義，不掛 SC marker）——「性質」selectbox 改用 format_func
顯示中文「資產/負債」，內部值仍為 HOLDING_KIND.ASSET="asset"/LIABILITY="liability"；
目標比重 number_input 的 label 加註「（%）」。這些皆不改變下層 Model/Service/Repository
的介面或值。既有項目的編輯入口（改名/改分類/改初始值後委派 HoldingRepository.update_holding）
亦屬此類——holding_id 穩定與改分類非時間版本化的業務正確性已由 test_holding_master.py 的
SC-003/SC-004 覆蓋，本檔只驗證 UI 到 Repository 呼叫邊界的資料傳遞，不重掛 marker。

初始市值/初始成本改用 amount_input（text_input＋整數千分位顯示），存檔時以 parse_amount
解析回 float，內部值語意不變。千分位顯示與逗號解析的業務規則本身已由 test_core_utils.py／
test_amount_widget.py 的 SC-081 覆蓋，本檔驗證的是設定頁把這兩個欄位接上 amount_input／
parse_amount 沒有接錯，故掛回 SC-081。

②SC-051（活存/定存分類初始成本預設帶入初始市值）——新增或編輯資產項目時，只要當下
分類為活存/定存，初始成本欄位即自動帶入與初始市值相同的數字，使用者仍可手動覆蓋。

③SC-057（新增與編輯持有項目可標記用途）——新增/編輯表單皆提供「用途」selectbox
（一般／購屋，預設一般），選取後的內部值為 HOLDING_PURPOSE.GENERAL="general"/
HOUSE="house"；純附加標記不受性質（資產/負債）分支限制，兩者皆可標記。

比照 test_input_view.py 的做法：以 AppTest 直接載入 views/settings.py，改以替身容器
（含最小可用替身）注入 session_state["container"]，脫離真實 Turso 依賴。
"""

# ==== 原生（標準庫） ====
from pathlib import Path
from types import SimpleNamespace

# ==== 第三方套件 ====
import libsql
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND, HOLDING_PURPOSE
from asset_lab.core.exceptions import PersistenceError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParamModel
from asset_lab.models.protocol import ProtocolThresholdModel
from asset_lab.repositories.connection_layers import CachingConnection, CountingConnection
from asset_lab.repositories.house_param_repository import HouseParamRepository
from asset_lab.repositories.protocol_threshold_repository import ProtocolThresholdRepository
from asset_lab.repositories.query_metrics import QueryMetrics
from asset_lab.repositories.read_cache import ReadCache
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.services.house_service import HouseService
from asset_lab.services.protocol_service import ProtocolService
from tests.flaky_connection import FlakyConnection

APP_DIR = Path(__file__).resolve().parent.parent


class _StubHoldingRepo:
    """主檔替身：可注入既有項目清單；add_holding / update_holding 呼叫會被記錄供斷言。"""

    def __init__(self, holdings: list[HoldingModel] | None = None):
        self._holdings = list(holdings) if holdings else []
        self.added: list[HoldingModel] = []
        self.updated: list[HoldingModel] = []

    def list_holdings(self):
        return self._holdings

    def add_holding(self, *, holding):
        self.added.append(holding)

    def update_holding(self, *, holding):
        self.updated.append(holding)


class _StubTargetRepo:
    """目標比重替身：無既有設定，供 _render_targets 讀取。"""

    def read_targets(self):
        return []

    def upsert_target(self, *, target):
        pass


class _StubProtocolThresholdRepo:
    """門檻替身：無既有保存值，ProtocolService 會補上預設值；整批寫入呼叫會被記錄。"""

    def __init__(self):
        self.batches: list[list] = []

    def read_thresholds(self):
        return []

    def upsert_thresholds(self, *, thresholds):
        self.batches.append(list(thresholds))


class _StubHouseParamRepo:
    """買房參數替身：無既有保存值，HouseService 會補上中性/方法論預設值；整批寫入會被記錄。"""

    def __init__(self):
        self.batches: list[list] = []

    def read_params(self):
        return []

    def upsert_params(self, *, params):
        self.batches.append(list(params))


def _run_app(
    *,
    holding_repo: _StubHoldingRepo | None = None,
    protocol_threshold_repo=None,
    house_param_repo=None,
) -> AppTest:
    """以替身容器跑 views/settings.py，回傳已 run() 完成的 AppTest。"""
    container = SimpleNamespace(
        holding_repo=holding_repo or _StubHoldingRepo(),
        target_repo=_StubTargetRepo(),
        protocol_threshold_repo=protocol_threshold_repo or _StubProtocolThresholdRepo(),
        protocol_service=ProtocolService(),
        house_param_repo=house_param_repo or _StubHouseParamRepo(),
        house_service=HouseService(),
    )
    at = AppTest.from_file(APP_DIR / "views" / "settings.py")
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
    """初始市值/初始成本輸入框以整數千分位顯示，不顯示小數；存檔後內部值仍為 float。"""

    @pytest.mark.scenario("SC-081")
    def test_market_value_and_cost_show_thousand_separator_display(self):
        at = _run_app()
        market_value = at.text_input(key="new_market_value")
        cost = at.text_input(key="new_cost")
        assert market_value.value == "0"
        assert cost.value == "0"

    @pytest.mark.scenario("SC-081")
    def test_market_value_and_cost_parse_to_float_on_save(self):
        repo = _StubHoldingRepo()
        at = _run_app(holding_repo=repo)
        at.text_input(key="new_name").set_value("測試項目").run()
        at.text_input(key="new_market_value").set_value("1,234,567").run()
        at.text_input(key="new_cost").set_value("500,000").run()
        add_button = next(b for b in at.button if b.label == "新增")
        add_button.click().run()
        assert repo.added[0].initial_market_value == 1234567.0
        assert repo.added[0].initial_cost == 500000.0


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
        at.text_input(key="new_market_value").set_value("123456").run()
        cost = at.text_input(key="new_cost")
        assert cost.value == "123,456"

    @pytest.mark.scenario("SC-051")
    def test_sc043_time_deposit_cost_follows_market_value(self):
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TIME_DEPOSIT).run()
        at.text_input(key="new_market_value").set_value("50000").run()
        cost = at.text_input(key="new_cost")
        assert cost.value == "50,000"

    @pytest.mark.scenario("SC-051")
    def test_sc043_user_can_still_manually_override_cost(self):
        # 自動帶入後使用者再手動改成別的值：改後的值須維持，不被覆蓋回市值
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        at.text_input(key="new_market_value").set_value("123456").run()
        at.text_input(key="new_cost").set_value("999").run()
        cost = at.text_input(key="new_cost")
        assert cost.value == "999"

    @pytest.mark.scenario("SC-051")
    def test_sc043_non_cash_category_cost_not_auto_filled(self):
        # 其他分類（股票/ETF 等）行為不變：改市值不影響成本欄位既有值
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TW_STOCK).run()
        at.text_input(key="new_market_value").set_value("500000").run()
        cost = at.text_input(key="new_cost")
        assert cost.value == "0"

    @pytest.mark.scenario("SC-051")
    def test_sc043_switching_from_cash_to_other_category_stops_auto_fill(self):
        # 從活存切回股票分類後，成本欄位不再隨市值自動帶入
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        at.text_input(key="new_market_value").set_value("123456").run()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TW_STOCK).run()
        at.text_input(key="new_market_value").set_value("777").run()
        cost = at.text_input(key="new_cost")
        assert cost.value == "123,456"

    @pytest.mark.scenario("SC-051")
    def test_sc043_switching_into_cash_category_syncs_existing_market_value(self):
        # 已在其他分類填好市值，才改選活存/定存：切換當下即以既有市值覆蓋成本欄位
        at = _run_app()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.TW_STOCK).run()
        at.text_input(key="new_market_value").set_value("500000").run()
        at.selectbox(key="new_cat").select(ASSET_CATEGORIES.DEMAND_DEPOSIT).run()
        cost = at.text_input(key="new_cost")
        assert cost.value == "500,000"


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
        at.text_input(key="edit_1_market_value").set_value("88000").run()
        cost = at.text_input(key="edit_1_cost")
        assert cost.value == "88,000"

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
        at.text_input(key="edit_2_market_value").set_value("150000").run()
        cost = at.text_input(key="edit_2_cost")
        assert cost.value == "150,000"

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
        at.text_input(key="edit_3_market_value").set_value("250000").run()
        at.text_input(key="edit_3_cost").set_value("210000").run()
        cost = at.text_input(key="edit_3_cost")
        assert cost.value == "210,000"

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
        at.text_input(key="edit_4_market_value").set_value("600000").run()
        cost = at.text_input(key="edit_4_cost")
        assert cost.value == "300,000"

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
        at.text_input(key="edit_8_market_value").set_value("120000").run()
        save_button = next(b for b in at.button if b.key == "edit_8_save")
        save_button.click().run()
        assert repo.updated[0].initial_market_value == 120000.0
        assert repo.updated[0].initial_cost == 120000.0


class TestNewHoldingPurposeSelectbox:
    """SC-057（新增流程）：新增持有項目可標記用途（一般／購屋），預設一般。"""

    @pytest.mark.scenario("SC-057")
    def test_sc057_purpose_options_are_chinese_labels_general_and_house_only(self):
        # 用途值域僅有「一般」與「購屋」兩種，介面不提供其他選項
        at = _run_app()
        purpose_select = at.selectbox(key="new_purpose")
        assert purpose_select.options == ["一般", "購屋"]

    @pytest.mark.scenario("SC-057")
    def test_sc057_default_purpose_is_general(self):
        # 新增時未特別選擇用途 → 預設為一般
        at = _run_app()
        purpose_select = at.selectbox(key="new_purpose")
        assert purpose_select.value == HOLDING_PURPOSE.GENERAL

    @pytest.mark.scenario("SC-057")
    def test_sc057_new_holding_with_house_purpose_selected_persists_house(self):
        repo = _StubHoldingRepo()
        at = _run_app(holding_repo=repo)
        at.text_input(key="new_name").set_value("範例定存").run()
        at.selectbox(key="new_purpose").select(HOLDING_PURPOSE.HOUSE).run()
        add_button = next(b for b in at.button if b.label == "新增")
        add_button.click().run()

        assert len(repo.added) == 1
        assert repo.added[0].purpose == HOLDING_PURPOSE.HOUSE

    @pytest.mark.scenario("SC-057")
    def test_sc057_new_holding_without_selecting_purpose_defaults_to_general(self):
        repo = _StubHoldingRepo()
        at = _run_app(holding_repo=repo)
        at.text_input(key="new_name").set_value("範例活存").run()
        add_button = next(b for b in at.button if b.label == "新增")
        add_button.click().run()

        assert repo.added[0].purpose == HOLDING_PURPOSE.GENERAL

    @pytest.mark.scenario("SC-057")
    def test_sc057_new_liability_does_not_show_purpose_selectbox_and_defaults_general(self):
        # 用途僅供買房 bucket 判斷資產是否計入購屋準備金，負債永不計入，故不顯示此欄位
        repo = _StubHoldingRepo()
        at = _run_app(holding_repo=repo)
        at.text_input(key="new_name").set_value("房貸")
        at.selectbox(key="new_kind").select(HOLDING_KIND.LIABILITY).run()

        with pytest.raises(KeyError):
            at.selectbox(key="new_purpose")

        add_button = next(b for b in at.button if b.label == "新增")
        add_button.click().run()

        assert repo.added[0].purpose == HOLDING_PURPOSE.GENERAL


class TestEditExistingHoldingPurposeSelectbox:
    """SC-057（編輯流程）：編輯既有項目可將用途從一般改為購屋、或反向改回。"""

    @pytest.mark.scenario("SC-057")
    def test_sc057_edit_purpose_selectbox_shows_current_value(self):
        holding = HoldingModel(
            holding_id=9,
            name="範例定存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            initial_market_value=600000.0,
            initial_cost=600000.0,
            purpose=HOLDING_PURPOSE.GENERAL,
        )
        at = _run_app(holding_repo=_StubHoldingRepo(holdings=[holding]))
        purpose_select = at.selectbox(key="edit_9_purpose")
        assert purpose_select.value == HOLDING_PURPOSE.GENERAL

    @pytest.mark.scenario("SC-057")
    def test_sc057_editing_purpose_from_general_to_house_persists(self):
        holding = HoldingModel(
            holding_id=10,
            name="範例定存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            initial_market_value=600000.0,
            initial_cost=600000.0,
            purpose=HOLDING_PURPOSE.GENERAL,
        )
        repo = _StubHoldingRepo(holdings=[holding])
        at = _run_app(holding_repo=repo)
        at.selectbox(key="edit_10_purpose").select(HOLDING_PURPOSE.HOUSE).run()
        save_button = next(b for b in at.button if b.key == "edit_10_save")
        save_button.click().run()

        assert repo.updated[0].purpose == HOLDING_PURPOSE.HOUSE

    @pytest.mark.scenario("SC-057")
    def test_sc057_editing_purpose_from_house_back_to_general_persists(self):
        holding = HoldingModel(
            holding_id=11,
            name="範例定存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            initial_market_value=600000.0,
            initial_cost=600000.0,
            purpose=HOLDING_PURPOSE.HOUSE,
        )
        repo = _StubHoldingRepo(holdings=[holding])
        at = _run_app(holding_repo=repo)
        at.selectbox(key="edit_11_purpose").select(HOLDING_PURPOSE.GENERAL).run()
        save_button = next(b for b in at.button if b.key == "edit_11_save")
        save_button.click().run()

        assert repo.updated[0].purpose == HOLDING_PURPOSE.GENERAL

    @pytest.mark.scenario("SC-057")
    def test_sc057_editing_other_fields_does_not_change_purpose(self):
        # 只改名字、不動用途：儲存後用途維持原值（購屋）
        holding = HoldingModel(
            holding_id=12,
            name="範例定存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            initial_market_value=600000.0,
            initial_cost=600000.0,
            purpose=HOLDING_PURPOSE.HOUSE,
        )
        repo = _StubHoldingRepo(holdings=[holding])
        at = _run_app(holding_repo=repo)
        at.text_input(key="edit_12_name").set_value("改名定存").run()
        save_button = next(b for b in at.button if b.key == "edit_12_save")
        save_button.click().run()

        assert repo.updated[0].name == "改名定存"
        assert repo.updated[0].purpose == HOLDING_PURPOSE.HOUSE

    @pytest.mark.scenario("SC-057")
    def test_sc057_liability_edit_does_not_show_purpose_selectbox(self):
        # 用途僅供買房 bucket 判斷資產是否計入購屋準備金，負債永不計入，故不顯示此欄位
        holding = HoldingModel(
            holding_id=13,
            name="房貸",
            kind=HOLDING_KIND.LIABILITY,
            category=None,
            initial_market_value=None,
            initial_cost=None,
            purpose=HOLDING_PURPOSE.GENERAL,
        )
        at = _run_app(holding_repo=_StubHoldingRepo(holdings=[holding]))
        with pytest.raises(KeyError):
            at.selectbox(key="edit_13_purpose")


def _click(at: AppTest, label: str) -> None:
    next(b for b in at.button if b.label == label).click().run()


class TestBatchSaveSuccess:
    """SC-128：門檻與買房參數各自整批一次寫入，成功顯示訊息；驗證失敗不進入寫入。"""

    @pytest.mark.scenario("SC-128")
    def test_sc128_save_thresholds_writes_three_rows_in_one_batch(self):
        repo = _StubProtocolThresholdRepo()
        at = _run_app(protocol_threshold_repo=repo)
        at.number_input(key="protocol_l1").set_value(10.0)
        at.number_input(key="protocol_l2").set_value(20.0)
        at.number_input(key="protocol_l3").set_value(30.0).run()

        _click(at, "儲存門檻")

        assert len(repo.batches) == 1
        assert [(m.level, m.drawdown_threshold) for m in repo.batches[0]] == [
            ("L1", 10.0),
            ("L2", 20.0),
            ("L3", 30.0),
        ]
        assert any("已儲存回撤門檻" in s.value for s in at.success)

    @pytest.mark.scenario("SC-128")
    def test_sc128_invalid_thresholds_do_not_enter_write(self):
        repo = _StubProtocolThresholdRepo()
        at = _run_app(protocol_threshold_repo=repo)
        at.number_input(key="protocol_l1").set_value(30.0)
        at.number_input(key="protocol_l2").set_value(20.0)
        at.number_input(key="protocol_l3").set_value(10.0).run()

        _click(at, "儲存門檻")

        assert repo.batches == []
        assert len(at.error) == 1

    @pytest.mark.scenario("SC-128")
    def test_sc128_save_house_params_writes_nine_rows_in_one_batch(self):
        repo = _StubHouseParamRepo()
        at = _run_app(house_param_repo=repo)
        at.text_input(key="house_target_total_price").set_value("10,000,000").run()

        _click(at, "儲存買房參數")

        assert len(repo.batches) == 1
        assert len(repo.batches[0]) == 9
        price = next(m for m in repo.batches[0] if m.param_key == "target_total_price")
        assert price.param_value == 10000000.0
        assert any("已儲存買房參數" in s.value for s in at.success)

    @pytest.mark.scenario("SC-128")
    def test_sc128_invalid_house_params_do_not_enter_write(self):
        repo = _StubHouseParamRepo()
        at = _run_app(house_param_repo=repo)
        at.number_input(key="house_loan_years").set_value(1).run()
        at.number_input(key="house_down_payment_ratio").set_value(0.0).run()

        _click(at, "儲存買房參數")

        assert repo.batches == []
        assert len(at.error) == 1


def _run_app_with_real_repos(conn) -> AppTest:
    """以真實 Repository（走傳入連線）組容器，其餘沿用替身。"""
    container = SimpleNamespace(
        holding_repo=_StubHoldingRepo(),
        target_repo=_StubTargetRepo(),
        protocol_threshold_repo=ProtocolThresholdRepository(conn=conn),
        protocol_service=ProtocolService(),
        house_param_repo=HouseParamRepository(conn=conn),
        house_service=HouseService(),
    )
    at = AppTest.from_file(APP_DIR / "views" / "settings.py")
    at.session_state["container"] = container
    at.run()
    return at


@pytest.fixture
def real_conn():
    connection = libsql.connect(":memory:")
    SchemaRepository(conn=connection).ensure_schema()
    return connection


_FRIENDLY_SAVE_FAILURE = "存檔失敗，資料未變更，請重試"


class TestBatchSaveFailure:
    """SC-129：整批存檔中途失敗，全部維持原值、只顯示友善訊息。"""

    @pytest.mark.scenario("SC-129")
    def test_sc129_threshold_failure_keeps_all_original_values(self, real_conn):
        ProtocolThresholdRepository(conn=real_conn).upsert_thresholds(
            thresholds=[
                ProtocolThresholdModel(level="L1", drawdown_threshold=10.0),
                ProtocolThresholdModel(level="L2", drawdown_threshold=20.0),
                ProtocolThresholdModel(level="L3", drawdown_threshold=30.0),
            ]
        )
        at = _run_app_with_real_repos(FlakyConnection(real_conn, fail_at=2))
        at.number_input(key="protocol_l1").set_value(15.0)
        at.number_input(key="protocol_l2").set_value(25.0)
        at.number_input(key="protocol_l3").set_value(35.0).run()

        _click(at, "儲存門檻")

        stored = {
            t.level: t.drawdown_threshold
            for t in ProtocolThresholdRepository(conn=real_conn).read_thresholds()
        }
        assert stored == {"L1": 10.0, "L2": 20.0, "L3": 30.0}
        assert [e.value for e in at.error] == [_FRIENDLY_SAVE_FAILURE]
        assert not at.exception
        assert not at.success

    @pytest.mark.scenario("SC-129")
    def test_sc129_house_param_failure_keeps_all_original_values(self, real_conn):
        original = [
            HouseParamModel(param_key=key, param_value=value)
            for key, value in (
                ("target_total_price", 1000000.0),
                ("target_year", 2040.0),
                ("monthly_after_tax_income", 80000.0),
                ("income_threshold", 50000.0),
                ("cash_floor", 100000.0),
                ("down_payment_ratio", 30.0),
                ("payment_cap_ratio", 35.0),
                ("test_annual_rate", 2.5),
                ("loan_years", 30.0),
            )
        ]
        HouseParamRepository(conn=real_conn).upsert_params(params=original)
        at = _run_app_with_real_repos(FlakyConnection(real_conn, fail_at=4))
        at.number_input(key="house_loan_years").set_value(20)
        at.number_input(key="house_target_year").set_value(2050).run()

        _click(at, "儲存買房參數")

        stored = {
            m.param_key: m.param_value
            for m in HouseParamRepository(conn=real_conn).read_params()
        }
        assert stored == {m.param_key: m.param_value for m in original}
        assert [e.value for e in at.error] == [_FRIENDLY_SAVE_FAILURE]
        assert not at.exception

    @pytest.mark.scenario("SC-129")
    def test_sc129_commit_and_rollback_failure_show_same_friendly_message(self, real_conn):
        flaky = FlakyConnection(real_conn, commit_fails=True, rollback_fails=True)
        at = _run_app_with_real_repos(flaky)
        at.number_input(key="protocol_l1").set_value(5.0).run()

        _click(at, "儲存門檻")

        assert [e.value for e in at.error] == [_FRIENDLY_SAVE_FAILURE]
        assert not at.exception


class TestBatchSaveFailureKeepsCache:
    """SC-129：整批存檔失敗時，讀取快取不被清除。"""

    @pytest.mark.scenario("SC-129")
    def test_sc129_failed_batch_write_does_not_clear_read_cache(self, real_conn):
        seed = ProtocolThresholdRepository(conn=real_conn)
        seed.upsert_thresholds(
            thresholds=[
                ProtocolThresholdModel(level="L1", drawdown_threshold=10.0),
                ProtocolThresholdModel(level="L2", drawdown_threshold=20.0),
                ProtocolThresholdModel(level="L3", drawdown_threshold=30.0),
            ]
        )
        metrics = QueryMetrics()
        stack = CachingConnection(
            inner=CountingConnection(
                inner=FlakyConnection(real_conn, fail_at=2), metrics=metrics
            ),
            cache=ReadCache(ttl_seconds=300),
            metrics=metrics,
        )
        repo = ProtocolThresholdRepository(conn=stack)
        repo.read_thresholds()  # 讓快取有資料
        metrics.take()

        with pytest.raises(PersistenceError):
            repo.upsert_thresholds(
                thresholds=[
                    ProtocolThresholdModel(level="L1", drawdown_threshold=15.0),
                    ProtocolThresholdModel(level="L2", drawdown_threshold=25.0),
                    ProtocolThresholdModel(level="L3", drawdown_threshold=35.0),
                ]
            )
        metrics.take()
        stored = repo.read_thresholds()

        assert metrics.take().cache_hits == 1
        assert [t.drawdown_threshold for t in stored] == [10.0, 20.0, 30.0]
