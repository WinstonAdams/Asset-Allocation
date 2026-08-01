"""總覽頁（views/overview.py）的呈現邏輯與落地頁切換測試（SC-049/050）。

views/*.py 為 Streamlit 頁面檔，模組尾端無條件呼叫 render()（觸發 st.session_state
存取的副作用），不適合在一般 pytest 情境下直接 import ——與既有頁面測法一致（見
tests/test_page_config.py：不 import 頁面模組本身，只驗證可獨立運作/可讀取原始碼的
部分）。本 Task 把「level_code→ProtocolLevelSpec 查表」與「ProtocolStatus→呈現資料」
的可測邏輯抽為純函式模組 asset_lab.overview_presentation（無 st.*、無 I/O，定位比照
asset_lab.charts），本檔直接測該模組；並對 constants.PROTOCOL_LEVELS 的內容斷言忠實
對齊協定「情境分級」表（SC-050）。落地頁切換（總覽取代月度錄入、default=True）以
app.py 原始碼掃描驗證，比照 test_navigation_guard/test_page_config 的 view/app 層測法。
"""

# ==== 原生（標準庫） ====
import re
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

# ==== 第三方套件 ====
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab import overview_presentation
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    HOLDING_PURPOSE,
    HOUSE_PARAM_KEY,
    HOUSE_TRIGGER,
    PROTOCOL_LEVEL_CODE,
    PROTOCOL_LEVELS,
)
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParamModel, SubjectiveTriggerModel
from asset_lab.models.results import (
    BucketProgress,
    ProtocolStatus,
    TriggerChecklist,
    TriggerCondition,
)
from asset_lab.overview_presentation import OverviewPresentation
from asset_lab.services.affordability_service import AffordabilityService
from asset_lab.services.house_service import HouseService

APP_DIR = Path(__file__).resolve().parent.parent
APP_PY = APP_DIR / "app.py"


def _status(
    *,
    level_code: str,
    status: str,
    drawdown: float | None,
    current_cumulative_twr: float | None = None,
    data_month_count: int = 5,
) -> ProtocolStatus:
    """組出測試用 ProtocolStatus（比照 ProtocolService.assess 的輸出形狀）。"""
    return ProtocolStatus(
        level_code=level_code,
        status=status,
        drawdown=drawdown,
        current_cumulative_twr=current_cumulative_twr,
        data_month_count=data_month_count,
    )


class TestProtocolLevelsContentAlignsWithProtocolTable:
    """PROTOCOL_LEVELS 內容須忠實對齊協定「情境分級與對應動作」表（SC-050）。"""

    @pytest.mark.scenario("SC-050")
    def test_sc050_four_levels_present_in_ascending_order(self):
        assert [spec.code for spec in PROTOCOL_LEVELS] == list(PROTOCOL_LEVEL_CODE.ALL)

    @pytest.mark.scenario("SC-050")
    def test_sc050_l0_must_do_and_label(self):
        l0 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L0)
        assert l0.label == "平時"
        assert l0.must_do == ("照計畫定期定額（依原訂投資計畫，不特別作為）",)

    @pytest.mark.scenario("SC-050")
    def test_sc050_l0_must_not_is_not_blank_and_states_no_special_prohibition(self):
        # L0「無特別禁止」不得呈現為空白造成誤解，需明示為平時姿態（設計邊界）
        l0 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L0)
        assert len(l0.must_not) > 0
        assert any("無特別禁止" in item for item in l0.must_not)

    @pytest.mark.scenario("SC-050")
    def test_sc050_l0_stays_clean_without_firewall_or_crash_wording(self):
        # 鎖定邊界：L0 平時不得出現行為防火牆或任何大跌應對提醒——那些只在系統
        # 真的判定進入 L1 以上時才有意義，避免與平時/資料不足的中性姿態混淆
        l0 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L0)
        for item in (*l0.must_do, *l0.must_not):
            assert "券商 App" not in item
            assert "行為防火牆" not in item

    @pytest.mark.scenario("SC-050")
    def test_sc050_l1_matches_protocol_table(self):
        l1 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L1)
        assert l1.label == "修正"
        assert l1.band_text == "−10% ~ −20%"
        assert l1.must_do == ("照常定期定額，什麼都不改",)
        assert l1.must_not == (
            "行為防火牆通則：只看本系統，不看券商 App",
            "增加看盤頻率",
            "閱讀「崩盤將至」類內容",
        )

    @pytest.mark.scenario("SC-050")
    def test_sc050_l2_matches_protocol_table(self):
        l2 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L2)
        assert l2.label == "熊市"
        assert l2.band_text == "−20% ~ −30%"
        assert l2.must_do == ("照常定期定額", "若配置偏離目標超過 5 個百分點，執行再平衡")
        assert l2.must_not == (
            "行為防火牆通則：只看本系統，不看券商 App",
            "賣出任何部位",
            "修改目標配置",
            "與人爭論行情",
        )

    @pytest.mark.scenario("SC-050")
    def test_sc050_l3_prohibitions_equal_l2_plus_cooldown(self):
        # 禁止＝同 L2（含行為防火牆提醒），外加「72 小時內不做任何新決定」
        l2 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L2)
        l3 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L3)
        assert l3.label == "深熊"
        assert l3.band_text == "−30% 以上"
        assert l3.must_not == (*l2.must_not, "72 小時內不做任何新決定")

    @pytest.mark.scenario("SC-050")
    @pytest.mark.parametrize(
        "code", [PROTOCOL_LEVEL_CODE.L1, PROTOCOL_LEVEL_CODE.L2, PROTOCOL_LEVEL_CODE.L3]
    )
    def test_sc050_l1_and_above_include_firewall_reminder(self, code):
        # 行為防火牆提醒（只看本系統、不看券商 App）自 L1 起皆須顯示
        spec = overview_presentation.level_spec_for(code)
        assert "行為防火牆通則：只看本系統，不看券商 App" in spec.must_not


class TestLevelSpecForLookup:
    """level_spec_for：依 level_code 查表取回展示規格（SC-049）。"""

    @pytest.mark.scenario("SC-049")
    @pytest.mark.parametrize("code", list(PROTOCOL_LEVEL_CODE.ALL))
    def test_sc049_lookup_returns_spec_with_matching_code(self, code):
        assert overview_presentation.level_spec_for(code).code == code


class TestResolvePresentationHappyPath:
    """resolve_presentation：資料充足、判定為 L2 時的呈現內容（SC-049 happy）。"""

    @pytest.mark.scenario("SC-049")
    def test_sc049_l2_shows_level_band_and_metrics(self):
        status = _status(
            level_code=PROTOCOL_LEVEL_CODE.L2,
            status="ok",
            drawdown=-0.25,
            current_cumulative_twr=0.08,
        )

        presentation = overview_presentation.resolve_presentation(status)

        assert presentation.level_spec.code == PROTOCOL_LEVEL_CODE.L2
        assert presentation.level_spec.label == "熊市"
        assert presentation.level_spec.band_text == "−20% ~ −30%"
        assert presentation.neutral_message is None
        assert presentation.show_alert is True
        assert presentation.drawdown_percent == pytest.approx(-25.0)

    @pytest.mark.scenario("SC-049")
    def test_sc049_l0_with_sufficient_data_has_no_alert(self):
        # 資料充足但判定仍為 L0（平時）：不觸發警示（警示只在 L1–L3 顯示）
        status = _status(level_code=PROTOCOL_LEVEL_CODE.L0, status="ok", drawdown=-0.02)

        presentation = overview_presentation.resolve_presentation(status)

        assert presentation.show_alert is False
        assert presentation.neutral_message is None
        assert presentation.drawdown_percent == pytest.approx(-2.0)


class TestResolvePresentationL3RuleTextOnly:
    """L3：僅顯示機動加碼的規則文字，不計算/顯示任何加碼金額或現金地板數字（SC-049 邊界）。"""

    @pytest.mark.scenario("SC-049")
    def test_sc049_l3_must_do_is_rule_reference_text_not_computed_amount(self):
        l3 = overview_presentation.level_spec_for(PROTOCOL_LEVEL_CODE.L3)
        assert any("機動加碼" in item for item in l3.must_do)
        # 規則文字只引用協定章節，不得內嵌任何金額數字（無貨幣符號/金額語彙）
        for item in l3.must_do:
            assert "$" not in item
            assert "元" not in item

    @pytest.mark.scenario("SC-049")
    def test_sc049_presentation_struct_carries_no_computed_amount_field(self):
        # 結構性鎖定：呈現資料不承載任何加碼金額/現金地板欄位，日後不得誤加
        field_names = {f.name for f in fields(OverviewPresentation)}
        assert field_names == {"level_spec", "show_alert", "neutral_message", "drawdown_percent"}

    @pytest.mark.scenario("SC-049")
    def test_sc049_l3_status_still_shows_alert_and_drawdown(self):
        status = _status(level_code=PROTOCOL_LEVEL_CODE.L3, status="ok", drawdown=-0.35)

        presentation = overview_presentation.resolve_presentation(status)

        assert presentation.show_alert is True
        assert presentation.drawdown_percent == pytest.approx(-35.0)


class TestResolvePresentationInsufficientData:
    """資料不足（no_data / insufficient_data）：退回 L0 姿態、不顯示回撤數值與警示，
    依情況顯示對應中性文案（SC-049 邊界，資料充足度旗標定義見 SC-045）。"""

    @pytest.mark.scenario("SC-049")
    def test_sc049_no_record_shows_l0_with_no_record_message_and_no_drawdown(self):
        status = _status(
            level_code=PROTOCOL_LEVEL_CODE.L0,
            status="no_data",
            drawdown=None,
            current_cumulative_twr=None,
            data_month_count=0,
        )

        presentation = overview_presentation.resolve_presentation(status)

        assert presentation.level_spec.code == PROTOCOL_LEVEL_CODE.L0
        assert presentation.show_alert is False
        assert presentation.drawdown_percent is None
        assert presentation.neutral_message == overview_presentation.NO_DATA_MESSAGE

    @pytest.mark.scenario("SC-049")
    def test_sc049_below_minimum_months_shows_l0_with_distinct_message(self):
        # 有資料但不足 3 個月：即使當月暴跌，仍不顯示回撤數值與警示
        status = _status(
            level_code=PROTOCOL_LEVEL_CODE.L0,
            status="insufficient_data",
            drawdown=None,
            current_cumulative_twr=-0.9,
            data_month_count=2,
        )

        presentation = overview_presentation.resolve_presentation(status)

        assert presentation.level_spec.code == PROTOCOL_LEVEL_CODE.L0
        assert presentation.show_alert is False
        assert presentation.drawdown_percent is None
        assert presentation.neutral_message == overview_presentation.INSUFFICIENT_DATA_MESSAGE

    @pytest.mark.scenario("SC-049")
    def test_sc049_no_data_and_insufficient_data_messages_are_distinct(self):
        # 兩種資料不足情境文案須不同，避免使用者混淆「完全無紀錄」與「已有但不足」
        no_data_message = overview_presentation.NO_DATA_MESSAGE
        insufficient_data_message = overview_presentation.INSUFFICIENT_DATA_MESSAGE
        assert no_data_message != insufficient_data_message


class TestOverviewIsDefaultLandingPage:
    """總覽取代「月度錄入」成為登入後預設落地頁（SC-049）。"""

    @pytest.mark.scenario("SC-049")
    def test_sc049_overview_view_file_exists(self):
        assert (APP_DIR / "views" / "overview.py").exists()

    @pytest.mark.scenario("SC-049")
    def test_sc049_overview_registered_as_first_page_with_default_true(self):
        app_source = APP_PY.read_text(encoding="utf-8")
        pages = re.findall(r'st\.Page\("views/([^"]+)"[^)]*\)', app_source)

        assert pages, "app.py 應以 st.navigation([st.Page(...), ...]) 註冊多頁"
        assert pages[0] == "overview.py"

        overview_registration = re.search(r'st\.Page\("views/overview\.py"[^)]*\)', app_source)
        assert overview_registration is not None
        assert "default=True" in overview_registration.group(0)

        # 僅總覽設為預設落地頁，避免 st.navigation 因多個 default=True 而拋錯
        assert app_source.count("default=True") == 1

    @pytest.mark.scenario("SC-049")
    def test_sc049_existing_pages_still_registered_after_reorder(self):
        app_source = APP_PY.read_text(encoding="utf-8")
        pages = set(re.findall(r'st\.Page\("views/([^"]+)"[^)]*\)', app_source))

        expected = {
            "overview.py",
            "input.py",
            "allocation.py",
            "returns.py",
            "protocol.py",
            "settings.py",
            "data_io.py",
        }
        assert expected <= pages


# ---------------------------------------------------------------------------
# 總覽頁買房進度摘要：SC-071
# ---------------------------------------------------------------------------


def _bucket_progress(progress_pct: float | None) -> BucketProgress:
    """組出測試用 BucketProgress（overview_summary 只關心 progress_pct，其餘填中性值）。"""
    return BucketProgress(
        bucket_value=0.0,
        target_amount=0.0,
        gap=0.0,
        progress_pct=progress_pct,
        years_to_target=None,
        reached_target_year=False,
        required_annual_accumulation=None,
    )


def _checklist(met_count: int, total: int = 5) -> TriggerChecklist:
    """組出測試用 TriggerChecklist（前 met_count 條 met=True，恰 total 條）。"""
    conditions = [
        TriggerCondition(key=f"cond_{i}", kind="objective", met=i < met_count)
        for i in range(total)
    ]
    return TriggerChecklist(conditions=conditions, met_count=met_count, all_met=met_count == total)


class TestHouseServiceOverviewSummary:
    """HouseService.overview_summary：彙總 bucket 進度% 與觸發 met_count/total（SC-071）。"""

    @pytest.mark.scenario("SC-071")
    def test_sc071_combines_bucket_progress_pct_and_trigger_count(self):
        service = HouseService()

        summary = service.overview_summary(
            bucket_progress=_bucket_progress(66.7), checklist=_checklist(3)
        )

        assert summary.bucket_progress_pct == pytest.approx(66.7)
        assert summary.triggers_met_count == 3
        assert summary.triggers_total == 5

    @pytest.mark.scenario("SC-071")
    def test_sc071_target_unset_progress_none_but_trigger_count_still_shown(self):
        # 目標總價未設定時 progress_pct 為 None，但觸發計數不受影響照常呈現（SC-071 邊界）
        service = HouseService()

        summary = service.overview_summary(
            bucket_progress=_bucket_progress(None), checklist=_checklist(2)
        )

        assert summary.bucket_progress_pct is None
        assert summary.triggers_met_count == 2
        assert summary.triggers_total == 5


class _StubHouseParamRepo:
    """買房參數替身：以 dict（key=HOUSE_PARAM_KEY 值域）注入已存參數。"""

    def __init__(self, params: dict[str, float]):
        self._params = params

    def read_params(self):
        return [
            HouseParamModel(param_key=key, param_value=float(value))
            for key, value in self._params.items()
        ]


class _StubHoldingRepo:
    """項目主檔替身：固定回傳注入的持有項目清單。"""

    def __init__(self, holdings: list[HoldingModel]):
        self._holdings = holdings

    def list_holdings(self):
        return self._holdings


class _StubRecordRepo:
    """月度紀錄替身：同時支援總覽頁用的 latest_year_month() 與買房編排用的 read_all()。"""

    def __init__(self, records_df: pd.DataFrame):
        self._records_df = records_df

    def read_all(self):
        return self._records_df

    def latest_year_month(self):
        if self._records_df.empty:
            return None
        return str(self._records_df["year_month"].max())


class _StubSubjectiveTriggerRepo:
    """主觀觸發替身：read_triggers 回傳已存勾選狀態；upsert_trigger 為無操作樁。"""

    def __init__(self, triggers: list[SubjectiveTriggerModel]):
        self._triggers = list(triggers)

    def read_triggers(self):
        return self._triggers

    def upsert_trigger(self, *, trigger):
        pass


_EMPTY_RECORDS_COLUMNS = ["holding_id", "year_month", "market_value", "net_investment"]


def _empty_records_df() -> pd.DataFrame:
    """空月度紀錄（尚無任何錄入），供 bucket 以 initial_market_value 起始市值計。"""
    return pd.DataFrame(columns=_EMPTY_RECORDS_COLUMNS)


def _house_holding_bucket_1m() -> HoldingModel:
    """一筆購屋標記定存，虛構起始市值 100 萬（無月度紀錄，bucket 以此起始值計）。"""
    return HoldingModel(
        holding_id=1,
        name="範例購屋定存",
        kind="asset",
        category=ASSET_CATEGORIES.TIME_DEPOSIT,
        purpose=HOLDING_PURPOSE.HOUSE,
        initial_market_value=1_000_000.0,
        initial_cost=1_000_000.0,
    )


def _house_summary_params(**overrides: float) -> dict[str, float]:
    """虛構買房參數：bucket 目標 150 萬（總價 500 萬 × 自備 30%），月付上限刻意壓低
    確保月付觸發不成立，供 SC-071 摘要測試組出「3/5」的可預期組合。"""
    base = {
        HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE: 5_000_000.0,
        HOUSE_PARAM_KEY.DOWN_PAYMENT_RATIO: 30.0,
        HOUSE_PARAM_KEY.INCOME_THRESHOLD: 50_000.0,
        HOUSE_PARAM_KEY.MONTHLY_AFTER_TAX_INCOME: 60_000.0,
        HOUSE_PARAM_KEY.PAYMENT_CAP_RATIO: 5.0,
        HOUSE_PARAM_KEY.TEST_ANNUAL_RATE: 2.5,
        HOUSE_PARAM_KEY.LOAN_YEARS: 30.0,
    }
    base.update(overrides)
    return base


def _house_summary_triggers() -> list[SubjectiveTriggerModel]:
    """定錨、認知兩條主觀觸發皆已勾選。"""
    return [
        SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True),
        SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=True),
    ]


def _house_summary_container(
    *,
    params: dict[str, float],
    holdings: list[HoldingModel],
    records_df: pd.DataFrame,
    triggers: list[SubjectiveTriggerModel],
) -> SimpleNamespace:
    """組出總覽頁/買房頁共用的替身容器（買房相關欄位一致，其餘依頁面各自需要的欄位為準）。"""
    return SimpleNamespace(
        house_param_repo=_StubHouseParamRepo(params),
        holding_repo=_StubHoldingRepo(holdings),
        record_repo=_StubRecordRepo(records_df),
        subjective_trigger_repo=_StubSubjectiveTriggerRepo(triggers),
        house_service=HouseService(),
        affordability_service=AffordabilityService(),
    )


def _run_overview_page(
    *,
    params: dict[str, float],
    holdings: list[HoldingModel],
    records_df: pd.DataFrame,
    triggers: list[SubjectiveTriggerModel],
) -> AppTest:
    """以替身容器跑 views/overview.py，回傳已 run() 完成的 AppTest。

    月度紀錄為空（無任何錄入）使總覽頁走「無資料」姿態分支，只需買房相關欄位即可
    完整渲染買房摘要列，不必額外替身 return_service/protocol_service 等既有依賴
    （比照 tests/test_house.py 的 _run_house_page 慣例：僅替身用得到的 Repository 層）。
    """
    at = AppTest.from_file("views/overview.py")
    at.session_state["container"] = _house_summary_container(
        params=params, holdings=holdings, records_df=records_df, triggers=triggers
    )
    at.run()
    return at


class TestOverviewPageHouseSummary:
    """總覽頁買房摘要列：bucket 進度% + 觸發 x/5，與既有協定等級摘要同層呈現（SC-071 happy）。"""

    @pytest.mark.scenario("SC-071")
    def test_sc071_shows_bucket_progress_percent_and_trigger_count(self):
        at = _run_overview_page(
            params=_house_summary_params(),
            holdings=[_house_holding_bucket_1m()],
            records_df=_empty_records_df(),
            triggers=_house_summary_triggers(),
        )

        assert not at.exception
        progress_metric = next(m for m in at.metric if m.label == "買房 bucket 進度")
        trigger_metric = next(m for m in at.metric if m.label == "買房觸發條件")
        assert progress_metric.value == "66.7%"
        assert trigger_metric.value == "3/5"


class TestOverviewPageHouseSummaryTargetUnset:
    """目標總價未設定（0）時：進度呈現未設定語意，觸發計數仍照常顯示（SC-071 邊界）。"""

    @pytest.mark.scenario("SC-071")
    def test_sc071_target_total_price_unset_progress_dash_trigger_count_still_shown(self):
        at = _run_overview_page(
            params=_house_summary_params(
                **{
                    HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE: 0.0,
                    HOUSE_PARAM_KEY.INCOME_THRESHOLD: 0.0,
                }
            ),
            holdings=[_house_holding_bucket_1m()],
            records_df=_empty_records_df(),
            triggers=_house_summary_triggers(),
        )

        assert not at.exception
        progress_metric = next(m for m in at.metric if m.label == "買房 bucket 進度")
        trigger_metric = next(m for m in at.metric if m.label == "買房觸發條件")
        assert progress_metric.value == "—"
        assert trigger_metric.value == "2/5"


class TestOverviewPageHouseSummaryMatchesHousePage:
    """摘要口徑與買房獨立頁完全一致：同一時點兩頁顯示的進度%與 x/5 數字相同（SC-071 邊界）。"""

    @pytest.mark.scenario("SC-071")
    def test_sc071_overview_and_house_page_show_identical_progress_and_trigger_count(self):
        params = _house_summary_params()
        holdings = [_house_holding_bucket_1m()]
        records_df = _empty_records_df()
        triggers = _house_summary_triggers()

        overview_at = _run_overview_page(
            params=params, holdings=holdings, records_df=records_df, triggers=triggers
        )
        house_at = AppTest.from_file("views/house.py")
        house_at.session_state["container"] = _house_summary_container(
            params=params, holdings=holdings, records_df=records_df, triggers=triggers
        )
        house_at.run()

        assert not overview_at.exception
        assert not house_at.exception

        overview_progress = next(
            m for m in overview_at.metric if m.label == "買房 bucket 進度"
        ).value
        house_progress = next(m for m in house_at.metric if m.label == "進度").value
        assert overview_progress == house_progress

        overview_trigger_count = next(
            m for m in overview_at.metric if m.label == "買房觸發條件"
        ).value
        house_trigger_count = next(m for m in house_at.metric if m.label == "達成計數").value
        assert overview_trigger_count == house_trigger_count
