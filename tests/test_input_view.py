"""月度錄入頁的行為測試：年月下拉、依錄入方式分派四個編輯器、本月紀錄表、寫入失敗訊息。

比照 test_page_config.py／test_navigation_guard.py 的做法：以 AppTest 直接載入
views/input.py（非透過 app.py 的守門與真實 Turso 容器），改以替身容器注入
session_state["container"]，並攔截 today_in_timezone 固定時鐘，脫離真實時鐘與網路依賴。

View 層只驗證「解析錄入方式 → 委派 Service 規劃 → Repository 寫入」的線路沒有接錯；
推算數學與業務規則已由 Service 層測試（test_cost_basis.py／test_balance_input.py／
test_monthly_input.py）覆蓋，這裡用真正的純運算 Service 搭配 Repository 替身，不重複
驗證業務規則，但仍掛回對應業務規則的 SC marker（同一規則允許多個 test 從不同層次覆蓋）。
年月下拉相關測試屬純 UI 機制，無新業務語義，不掛 SC marker。
"""

# ==== 原生（標準庫） ====
from datetime import date
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    BALANCE_INPUT,
    COST_BASIS_INPUT,
    HOLDING_KIND,
    INPUT_MODE,
    PREMIUM_INPUT,
)
from asset_lab.core.exceptions import PersistenceError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.services.balance_input_service import BalanceInputService
from asset_lab.services.cost_basis_service import CostBasisService
from asset_lab.services.monthly_input_service import MonthlyInputService

# 替身主檔的 holding_id：活存／定存走餘額、台積電走總成本、保單走累計保費、信用卡／房貸為負債、
# 舊匯入項目分類留空。
_DEMAND_ID = 1
_TIME_ID = 2
_STOCK_ID = 10
_INSURANCE_ID = 30
_CARD_ID = 40
_LOAN_ID = 50
_UNCATEGORIZED_ID = 60

_FRIENDLY_WRITE_FAILURE = "存檔失敗，資料未變更，請重試"


def _holdings() -> list[HoldingModel]:
    return [
        HoldingModel(
            holding_id=_DEMAND_ID,
            name="活存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.DEMAND_DEPOSIT,
            initial_market_value=500000.0,
        ),
        HoldingModel(
            holding_id=_TIME_ID,
            name="定存",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
        ),
        HoldingModel(
            holding_id=_STOCK_ID,
            name="台積電",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_cost=300000.0,
        ),
        HoldingModel(
            holding_id=_INSURANCE_ID,
            name="海外年金保單",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.INSURANCE,
        ),
        HoldingModel(holding_id=_CARD_ID, name="信用卡", kind=HOLDING_KIND.LIABILITY),
        HoldingModel(holding_id=_LOAN_ID, name="房貸", kind=HOLDING_KIND.LIABILITY),
        HoldingModel(
            holding_id=_UNCATEGORIZED_ID,
            name="舊匯入項目",
            kind=HOLDING_KIND.ASSET,
            category=None,
        ),
    ]


class _StubHoldingRepo:
    """主檔替身：固定回傳涵蓋四種錄入方式與未分類項目的清單。"""

    def list_holdings(self):
        return _holdings()


class _StubRecordRepo:
    """記錄層替身：不觸真實 I/O，記錄寫入呼叫；可設定 failure 模擬寫入失敗。"""

    def __init__(self):
        self.upserted: list[object] = []
        self.deleted_single: list[tuple] = []
        self.batch_upserted: list[object] = []
        self.deleted_and_upserted: list[tuple] = []
        self.holding_records: dict[int, list[MonthlyRecordModel]] = {}
        self.month_records: dict[str, list[MonthlyRecordModel]] = {}
        self.failure: Exception | None = None

    def upsert_record(self, *, record):
        self.upserted.append(record)

    def delete_record(self, *, holding_id, year_month):
        self.deleted_single.append((holding_id, year_month))

    def upsert_records(self, *, records):
        if self.failure is not None:
            raise self.failure
        self.batch_upserted.extend(records)

    def delete_record_and_upsert(self, *, holding_id, year_month, records):
        if self.failure is not None:
            raise self.failure
        self.deleted_and_upserted.append((holding_id, year_month, records))

    def read_holding_records(self, *, holding_id):
        return list(self.holding_records.get(holding_id, []))

    def read_month(self, *, year_month):
        return list(self.month_records.get(year_month, []))


@pytest.fixture
def record_repo():
    """每個測試獨立的記錄層替身。"""
    return _StubRecordRepo()


class _SpyMonthlyInputService:
    """服務替身：記錄帶入呼叫；其餘純運算方法委派真實 Service（不碰 Repo）。"""

    def __init__(self):
        self.prefill_calls: list[str] = []
        self._real = MonthlyInputService(
            holding_repo=None,
            record_repo=None,
            input_mode_by_category=INPUT_MODE.BY_ASSET_CATEGORY,
            liability_kind=HOLDING_KIND.LIABILITY,
            liability_input_mode=INPUT_MODE.AMOUNT_DUE,
        )

    def resolve_input_mode(self, **kwargs):
        return self._real.resolve_input_mode(**kwargs)

    def build_amount_due_record(self, **kwargs):
        return self._real.build_amount_due_record(**kwargs)

    def build_record_prefill(self, **kwargs):
        return self._real.build_record_prefill(**kwargs)

    def summarize_month(self, **kwargs):
        return self._real.summarize_month(**kwargs)

    def prefill_from_previous(self, *, target_ym: str):
        self.prefill_calls.append(target_ym)
        return []


class _SpyCostBasisService(CostBasisService):
    """真實 CostBasisService，另記錄保險規劃是否被呼叫（必填留空時不得呼叫）。"""

    def __init__(self):
        super().__init__(
            cost_basis_categories=COST_BASIS_INPUT.CATEGORIES,
            premium_categories=PREMIUM_INPUT.CATEGORIES,
        )
        self.plan_save_premium_calls = 0

    def plan_save_premium(self, **kwargs):
        self.plan_save_premium_calls += 1
        return super().plan_save_premium(**kwargs)


def _run_app(
    *,
    today: date = date(2026, 5, 15),
    service=None,
    record_repo=None,
    cost_basis_service=None,
    holding_id: int | None = None,
) -> AppTest:
    """以固定時鐘與替身容器跑 views/input.py；指定 holding_id 時再選定該項目。"""
    container = SimpleNamespace(
        record_repo=record_repo or _StubRecordRepo(),
        holding_repo=_StubHoldingRepo(),
        monthly_input_service=service or _SpyMonthlyInputService(),
        cost_basis_service=cost_basis_service or _SpyCostBasisService(),
        balance_input_service=BalanceInputService(balance_categories=BALANCE_INPUT.CATEGORIES),
    )
    with mock.patch("asset_lab.services.period_service.today_in_timezone", return_value=today):
        at = AppTest.from_file("views/input.py")
        at.session_state["container"] = container
        at.run()
        if holding_id is not None:
            _select_holding(at, holding_id)
    return at


def _select_holding(at: AppTest, holding_id: int) -> None:
    next(sb for sb in at.selectbox if sb.label == "項目").set_value(holding_id).run()


def _click(at: AppTest, label: str) -> None:
    next(b for b in at.button if b.label == label).click().run()


def _keys(at: AppTest) -> set[str]:
    return {ti.key for ti in at.text_input}


def _all_written_text(at: AppTest) -> set[str]:
    """彙總 markdown 輸出文字，供斷言預覽內容用。"""
    return {m.value for m in at.markdown}


def _page_text(at: AppTest) -> str:
    """彙總頁面上所有文字型元素，供斷言某段文字完全不出現。"""
    elements = [
        *at.markdown,
        *at.caption,
        *at.info,
        *at.warning,
        *at.error,
        *at.success,
        *at.subheader,
    ]
    return "\n".join(str(e.value) for e in elements)


def _rec(holding_id, ym, **kw):
    return MonthlyRecordModel(holding_id=holding_id, year_month=ym, **kw)


class TestDefaultMonthDropdown:
    """年+月下拉預設帶入當月，且依 Asia/Taipei 時區判定（由呼叫端注入的固定日期驗證）。"""

    def test_default_selectboxes_show_current_month_in_timezone(self):
        at = _run_app(today=date(2026, 3, 15))
        assert not at.exception
        assert at.selectbox(key="input_target_year").value == 2026
        assert at.selectbox(key="input_target_month").value == 3

    def test_default_selectboxes_cross_year_boundary(self):
        at = _run_app(today=date(2026, 1, 1))
        assert at.selectbox(key="input_target_year").value == 2026
        assert at.selectbox(key="input_target_month").value == 1

    def test_default_selectboxes_end_of_year(self):
        at = _run_app(today=date(2025, 12, 31))
        assert at.selectbox(key="input_target_year").value == 2025
        assert at.selectbox(key="input_target_month").value == 12


class TestYearDropdownBounded:
    """年份下拉為當年往前推固定年數的有界範圍，不含未來年份。"""

    def test_year_options_bounded_around_current_year(self):
        at = _run_app(today=date(2026, 6, 1))
        year_select = at.selectbox(key="input_target_year")
        assert year_select.options == [str(y) for y in range(2021, 2027)]

    def test_month_options_cover_all_twelve_months(self):
        at = _run_app(today=date(2026, 6, 1))
        month_select = at.selectbox(key="input_target_month")
        assert month_select.options == [f"{m:02d}" for m in range(1, 13)]


class TestSelectedMonthPassedDownstream:
    """使用者變更年月下拉後，選定值正確組成 'YYYY-MM' 傳給既有下游服務呼叫。"""

    def test_prefill_button_passes_selected_year_month(self):
        service = _SpyMonthlyInputService()
        at = _run_app(today=date(2026, 3, 15), service=service)
        at.selectbox(key="input_target_year").set_value(2024)
        at.selectbox(key="input_target_month").set_value(11)
        _click(at, "帶入上月仍持有項目")
        assert service.prefill_calls[-1] == "2024-11"

    @pytest.mark.scenario("SC-087")
    def test_balance_save_uses_selected_year_month(self, record_repo):
        at = _run_app(today=date(2026, 3, 15), record_repo=record_repo)
        at.selectbox(key="input_target_year").set_value(2025)
        at.selectbox(key="input_target_month").set_value(7).run()
        at.text_input(key="balance_amount").set_value("400000").run()
        _click(at, "儲存此列")
        assert record_repo.batch_upserted[0].year_month == "2025-07"


class TestRecordEditorDispatch:
    """選定項目後依錄入方式分派編輯器，每種方式只顯示自己的欄位。"""

    @pytest.mark.scenario("SC-087")
    def test_balance_holding_shows_only_balance_field(self):
        at = _run_app(holding_id=_DEMAND_ID)
        assert {"balance_amount"} == _keys(at)
        assert at.text_input(key="balance_amount").label == "餘額"

    @pytest.mark.scenario("SC-099")
    def test_premium_holding_shows_three_premium_fields(self):
        at = _run_app(holding_id=_INSURANCE_ID)
        assert {"premium_cumulative_premium", "premium_surrender_value", "premium_withdrawal"} == (
            _keys(at)
        )
        assert at.text_input(key="premium_cumulative_premium").label == "累計已繳保費"
        assert at.text_input(key="premium_surrender_value").label == "解約金"

    @pytest.mark.scenario("SC-074")
    def test_stock_holding_shows_cost_basis_fields(self):
        at = _run_app(holding_id=_STOCK_ID)
        assert {
            "cost_basis_total_cost",
            "cost_basis_market_value",
            "cost_basis_realized_pnl",
            "cost_basis_cash_dividend",
        } == _keys(at)

    @pytest.mark.scenario("SC-101")
    def test_liability_holding_shows_only_amount_due_field(self):
        at = _run_app(holding_id=_CARD_ID)
        assert {"amount_due_amount"} == _keys(at)
        assert at.text_input(key="amount_due_amount").label == "應繳金額"

    @pytest.mark.scenario("SC-087")
    def test_no_manual_net_investment_field_for_any_holding(self):
        for holding_id in (
            _DEMAND_ID,
            _TIME_ID,
            _STOCK_ID,
            _INSURANCE_ID,
            _CARD_ID,
            _LOAN_ID,
        ):
            at = _run_app(holding_id=holding_id)
            assert "record_net_investment" not in _keys(at)
            assert "record_market_value" not in _keys(at)

    @pytest.mark.scenario("SC-102")
    def test_uncategorized_asset_shows_error_and_no_editor(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_UNCATEGORIZED_ID)

        assert any("請先到設定頁指定分類" in e.value for e in at.error)
        assert _keys(at) == set()
        assert not any(b.label == "儲存此列" for b in at.button)
        assert record_repo.batch_upserted == []
        assert record_repo.upserted == []

    @pytest.mark.scenario("SC-102")
    def test_assigning_category_restores_editor(self):
        # 切回已分類項目後，錯誤消失並恢復該分類的錄入欄位
        at = _run_app(holding_id=_UNCATEGORIZED_ID)
        _select_holding(at, _DEMAND_ID)
        assert not at.error
        assert "balance_amount" in _keys(at)


class TestNoTransferUi:
    """月度錄入頁沒有項目間轉移功能與相關提示。"""

    @pytest.mark.scenario("SC-103")
    @pytest.mark.parametrize(
        "holding_id",
        [_DEMAND_ID, _STOCK_ID, _INSURANCE_ID, _CARD_ID],
        ids=["balance", "stock", "premium", "amount_due"],
    )
    def test_page_has_no_transfer_section_or_hint(self, holding_id):
        at = _run_app(holding_id=holding_id)

        assert "轉移" not in _page_text(at)
        assert not any(b.label == "建立轉移" for b in at.button)
        assert {"src", "dst", "amt"}.isdisjoint(_keys(at))
        assert not any(sb.key in ("src", "dst") for sb in at.selectbox)

    @pytest.mark.scenario("SC-090")
    def test_stock_editor_has_no_transfer_hint_next_to_realized_fields(self):
        at = _run_app(holding_id=_STOCK_ID)
        assert not any("轉移" in c.value or "重複計入" in c.value for c in at.caption)

    @pytest.mark.scenario("SC-103")
    def test_header_hint_describes_updating_both_ends_instead_of_transfer(self):
        at = _run_app()
        info = "\n".join(i.value for i in at.info)
        assert "賣出" in info
        assert "淨投入記為負的提領金額" not in info
        assert "轉移" not in info


class TestBalanceEditor:
    """活存/定存：只填餘額，預覽前期餘額與推算淨投入，存檔與刪除走批次寫入。"""

    @pytest.mark.scenario("SC-087")
    def test_existing_record_prefills_balance(self, record_repo):
        record_repo.month_records["2026-05"] = [
            _rec(_DEMAND_ID, "2026-05", market_value=350000.0, net_investment=-150000.0)
        ]
        at = _run_app(record_repo=record_repo)
        assert at.text_input(key="balance_amount").value == "350,000"

    @pytest.mark.scenario("SC-087")
    def test_save_without_edit_keeps_existing_balance_and_net_investment(self, record_repo):
        record_repo.month_records["2026-05"] = [
            _rec(_DEMAND_ID, "2026-05", market_value=350000.0, net_investment=-150000.0)
        ]
        record_repo.holding_records[_DEMAND_ID] = record_repo.month_records["2026-05"]
        at = _run_app(record_repo=record_repo)
        _click(at, "儲存此列")

        saved = record_repo.batch_upserted[0]
        assert saved.market_value == 350000.0
        # 前期餘額取主檔初始市值 500000 → 350000 − 500000
        assert saved.net_investment == -150000.0
        assert record_repo.upserted == []

    @pytest.mark.scenario("SC-087")
    def test_no_record_leaves_balance_blank_and_blank_save_is_rejected(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_TIME_ID)
        assert at.text_input(key="balance_amount").value == ""

        _click(at, "儲存此列")

        assert record_repo.batch_upserted == []
        assert at.error

    @pytest.mark.scenario("SC-087")
    def test_blank_balance_on_existing_record_prefills_blank_not_zero(self, record_repo):
        record_repo.month_records["2026-05"] = [
            _rec(_DEMAND_ID, "2026-05", market_value=None, net_investment=-100000.0)
        ]
        at = _run_app(record_repo=record_repo)
        assert at.text_input(key="balance_amount").value == ""

    @pytest.mark.scenario("SC-087")
    def test_switching_month_reprefills_balance(self, record_repo):
        record_repo.month_records["2026-04"] = [
            _rec(_DEMAND_ID, "2026-04", market_value=500000.0, net_investment=0.0)
        ]
        at = _run_app(record_repo=record_repo)
        assert at.text_input(key="balance_amount").value == ""
        at.selectbox(key="input_target_month").set_value(4).run()
        assert at.text_input(key="balance_amount").value == "500,000"

    @pytest.mark.scenario("SC-087")
    def test_unsaved_input_survives_rerun_without_switching(self):
        at = _run_app()
        at.text_input(key="balance_amount").set_value("999").run()
        at.run()
        assert at.text_input(key="balance_amount").value == "999"

    @pytest.mark.scenario("SC-103")
    def test_preview_and_save_derive_net_investment_from_balance_change(self, record_repo):
        # 前期餘額 500000（2026-04）→ 本月填 400000 → 淨投入 −100000
        earlier = [_rec(_DEMAND_ID, "2026-04", market_value=500000.0, net_investment=0.0)]
        record_repo.holding_records[_DEMAND_ID] = earlier
        at = _run_app(record_repo=record_repo)
        at.text_input(key="balance_amount").set_value("400000").run()

        written = _all_written_text(at)
        assert "前期餘額：500,000" in written
        assert "推算本月淨投入：-100,000" in written

        _click(at, "儲存此列")
        saved = record_repo.batch_upserted[0]
        assert saved.holding_id == _DEMAND_ID
        assert saved.year_month == "2026-05"
        assert saved.market_value == 400000.0
        assert saved.net_investment == -100000.0

    @pytest.mark.scenario("SC-103")
    def test_save_also_writes_recalculated_next_row(self, record_repo):
        # 2026-06 的前期餘額會因本月改填而變動，連動重算的下一筆需一併寫入同一批次
        record_repo.holding_records[_DEMAND_ID] = [
            _rec(_DEMAND_ID, "2026-04", market_value=500000.0, net_investment=0.0),
            _rec(_DEMAND_ID, "2026-06", market_value=450000.0, net_investment=-50000.0),
        ]
        at = _run_app(record_repo=record_repo)
        at.text_input(key="balance_amount").set_value("400000").run()
        _click(at, "儲存此列")

        assert [r.year_month for r in record_repo.batch_upserted] == ["2026-05", "2026-06"]
        assert record_repo.batch_upserted[1].net_investment == 50000.0

    @pytest.mark.scenario("SC-087")
    def test_incomplete_input_shows_placeholder_instead_of_crashing(self):
        at = _run_app()
        assert not at.exception
        assert any("輸入完成後顯示推算值" in c.value for c in at.caption)

    @pytest.mark.scenario("SC-103")
    def test_delete_delegates_to_plan_delete_then_delete_record_and_upsert(self, record_repo):
        at = _run_app(record_repo=record_repo)
        _click(at, "刪除此列")

        assert record_repo.deleted_and_upserted == [(_DEMAND_ID, "2026-05", [])]
        assert record_repo.deleted_single == []


class TestPremiumEditor:
    """保險：累計已繳保費＋解約金＋本月領回，必填留空不呼叫規劃，領回為負被拒絕。"""

    @staticmethod
    def _insured_repo() -> _StubRecordRepo:
        record_repo = _StubRecordRepo()
        record_repo.holding_records[_INSURANCE_ID] = [
            _rec(
                _INSURANCE_ID,
                "2026-05",
                market_value=580000.0,
                net_investment=20000.0,
                total_cost=620000.0,
                realized_income=0.0,
            )
        ]
        return record_repo

    @pytest.mark.scenario("SC-099")
    def test_existing_record_prefills_three_fields(self):
        at = _run_app(record_repo=self._insured_repo(), holding_id=_INSURANCE_ID)
        assert at.text_input(key="premium_cumulative_premium").value == "620,000"
        assert at.text_input(key="premium_surrender_value").value == "580,000"
        assert at.text_input(key="premium_withdrawal").value == "0"

    @pytest.mark.scenario("SC-099")
    def test_save_without_edit_keeps_record_values(self):
        record_repo = self._insured_repo()
        at = _run_app(record_repo=record_repo, holding_id=_INSURANCE_ID)
        _click(at, "儲存此列")

        saved = record_repo.batch_upserted[0]
        assert saved.total_cost == 620000.0
        assert saved.market_value == 580000.0
        assert saved.realized_income == 0.0

    @pytest.mark.scenario("SC-099")
    def test_month_without_record_blanks_required_fields_and_defaults_withdrawal_zero(self):
        at = _run_app(record_repo=self._insured_repo(), holding_id=_INSURANCE_ID)
        at.selectbox(key="input_target_month").set_value(6).run()

        assert at.text_input(key="premium_cumulative_premium").value == ""
        assert at.text_input(key="premium_surrender_value").value == ""
        assert at.text_input(key="premium_withdrawal").value == "0"

    @pytest.mark.scenario("SC-099")
    def test_existing_record_with_blank_premium_prefills_blank_not_zero(self, record_repo):
        record_repo.holding_records[_INSURANCE_ID] = [
            _rec(_INSURANCE_ID, "2026-05", market_value=None, total_cost=None)
        ]
        at = _run_app(record_repo=record_repo, holding_id=_INSURANCE_ID)
        assert at.text_input(key="premium_cumulative_premium").value == ""
        assert at.text_input(key="premium_surrender_value").value == ""

    @pytest.mark.scenario("SC-096")
    @pytest.mark.scenario("SC-099")
    @pytest.mark.parametrize(
        ("premium", "surrender"),
        [("", ""), ("", "585000"), ("620000", "")],
        ids=["both_blank", "only_premium_blank", "only_surrender_blank"],
    )
    def test_save_with_blank_required_field_is_rejected_without_planning(
        self, record_repo, premium, surrender
    ):
        service = _SpyCostBasisService()
        at = _run_app(record_repo=record_repo, cost_basis_service=service, holding_id=_INSURANCE_ID)
        if premium:
            at.text_input(key="premium_cumulative_premium").set_value(premium).run()
        if surrender:
            at.text_input(key="premium_surrender_value").set_value(surrender).run()
        _click(at, "儲存此列")

        assert at.error
        assert service.plan_save_premium_calls == 0
        assert record_repo.batch_upserted == []

    @pytest.mark.scenario("SC-096")
    def test_negative_withdrawal_shows_reason_in_preview_and_rejects_save(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_INSURANCE_ID)
        at.text_input(key="premium_cumulative_premium").set_value("620000").run()
        at.text_input(key="premium_surrender_value").set_value("585000").run()
        at.text_input(key="premium_withdrawal").set_value("-1000").run()

        assert any("領回金額不可為負" in e.value for e in at.error)
        assert not any("輸入完成後顯示推算值" in c.value for c in at.caption)

        _click(at, "儲存此列")
        assert record_repo.batch_upserted == []
        assert any("領回金額不可為負" in e.value for e in at.error)

    @pytest.mark.scenario("SC-096")
    def test_zero_withdrawal_is_valid(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_INSURANCE_ID)
        at.text_input(key="premium_cumulative_premium").set_value("620000").run()
        at.text_input(key="premium_surrender_value").set_value("585000").run()
        assert not at.error

    @pytest.mark.scenario("SC-099")
    def test_preview_and_save_use_premium_derivation(self, record_repo):
        # 前期累計保費 600000（2026-04 新制列），本月 620000、領回 5000 → (620000−600000)−5000
        record_repo.holding_records[_INSURANCE_ID] = [
            _rec(
                _INSURANCE_ID,
                "2026-04",
                market_value=570000.0,
                net_investment=0.0,
                total_cost=600000.0,
                realized_income=0.0,
            )
        ]
        at = _run_app(record_repo=record_repo, holding_id=_INSURANCE_ID)
        at.text_input(key="premium_cumulative_premium").set_value("620000").run()
        at.text_input(key="premium_surrender_value").set_value("585000").run()
        at.text_input(key="premium_withdrawal").set_value("5000").run()

        written = _all_written_text(at)
        assert "前期累計保費：600,000" in written
        assert "推算本月淨投入：15,000" in written

        _click(at, "儲存此列")
        saved = record_repo.batch_upserted[0]
        assert saved.holding_id == _INSURANCE_ID
        assert saved.total_cost == 620000.0
        assert saved.market_value == 585000.0
        assert saved.realized_income == 5000.0
        assert saved.net_investment == 15000.0

    @pytest.mark.scenario("SC-099")
    def test_delete_delegates_to_plan_delete_then_delete_record_and_upsert(self):
        record_repo = self._insured_repo()
        at = _run_app(record_repo=record_repo, holding_id=_INSURANCE_ID)
        _click(at, "刪除此列")

        assert record_repo.deleted_and_upserted == [(_INSURANCE_ID, "2026-05", [])]


class TestCostBasisPreviewAndDelegation:
    """股票/ETF：存檔前預覽、儲存與刪除，委派 CostBasisService／Repository。"""

    @pytest.mark.scenario("SC-074")
    def test_preview_shows_previous_total_cost_and_derived_investment(self):
        at = _run_app(holding_id=_STOCK_ID)
        at.text_input(key="cost_basis_total_cost").set_value("0").run()
        written = _all_written_text(at)
        assert "前期總成本：300,000" in written
        assert "推算本月淨投入：-300,000" in written

    @pytest.mark.scenario("SC-074")
    def test_incomplete_input_shows_placeholder_instead_of_crashing(self):
        at = _run_app(holding_id=_STOCK_ID)
        at.text_input(key="cost_basis_total_cost").set_value("").run()

        assert not at.exception
        assert any("輸入完成後顯示推算值" in c.value for c in at.caption)

    @pytest.mark.scenario("SC-074")
    def test_save_button_delegates_to_plan_save_then_batch_upsert(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_STOCK_ID)
        at.text_input(key="cost_basis_total_cost").set_value("350000").run()
        at.text_input(key="cost_basis_market_value").set_value("400000").run()
        _click(at, "儲存此列")

        assert len(record_repo.batch_upserted) == 1
        saved = record_repo.batch_upserted[0]
        assert saved.holding_id == _STOCK_ID
        assert saved.year_month == "2026-05"
        assert saved.total_cost == 350000.0
        assert saved.market_value == 400000.0
        assert saved.net_investment == 50000.0

    @pytest.mark.scenario("SC-075")
    def test_transition_estimate_warning_shown_in_preview(self, record_repo):
        # 初始成本 300000 + 兩筆舊制列淨投入 30000、20000 → 前期總成本估算 350000
        record_repo.holding_records[_STOCK_ID] = [
            _rec(_STOCK_ID, "2026-03", net_investment=30000.0),
            _rec(_STOCK_ID, "2026-04", net_investment=20000.0),
        ]
        at = _run_app(record_repo=record_repo, holding_id=_STOCK_ID)
        at.text_input(key="cost_basis_total_cost").set_value("380000").run()

        written = _all_written_text(at)
        assert "前期總成本：350,000" in written
        assert "推算本月淨投入：30,000" in written
        assert any("過渡期估算" in w.value for w in at.warning)

    @pytest.mark.scenario("SC-077")
    def test_delete_button_delegates_to_plan_delete_then_delete_record_and_upsert(
        self, record_repo
    ):
        at = _run_app(record_repo=record_repo, holding_id=_STOCK_ID)
        _click(at, "刪除此列")

        assert record_repo.deleted_and_upserted == [(_STOCK_ID, "2026-05", [])]


class TestCostBasisPrefillAndDividendFields:
    """股票/ETF 錄入框帶入既有值（兩格分開）、兩欄輸入、股利負值拒絕。"""

    @staticmethod
    def _stock_repo_with_record() -> _StubRecordRepo:
        record_repo = _StubRecordRepo()
        record_repo.holding_records[_STOCK_ID] = [
            _rec(
                _STOCK_ID,
                "2026-05",
                market_value=650000.0,
                net_investment=0.0,
                total_cost=600000.0,
                realized_income=11500.0,
                cash_dividend=1500.0,
            )
        ]
        return record_repo

    @pytest.mark.scenario("SC-088")
    def test_existing_record_prefills_four_fields_separately(self):
        at = _run_app(record_repo=self._stock_repo_with_record(), holding_id=_STOCK_ID)
        assert at.text_input(key="cost_basis_total_cost").value == "600,000"
        assert at.text_input(key="cost_basis_market_value").value == "650,000"
        assert at.text_input(key="cost_basis_realized_pnl").value == "10,000"
        assert at.text_input(key="cost_basis_cash_dividend").value == "1,500"

    @pytest.mark.scenario("SC-088")
    def test_switching_to_month_without_record_blanks_cost_and_value(self):
        at = _run_app(record_repo=self._stock_repo_with_record(), holding_id=_STOCK_ID)
        at.selectbox(key="input_target_month").set_value(6).run()
        for key in ("cost_basis_total_cost", "cost_basis_market_value"):
            assert at.text_input(key=key).value == ""
        for key in ("cost_basis_realized_pnl", "cost_basis_cash_dividend"):
            assert at.text_input(key=key).value == "0"

    @pytest.mark.scenario("SC-088")
    @pytest.mark.parametrize(
        ("total_cost", "market_value"),
        [("", ""), ("", "650000"), ("600000", "")],
        ids=["both_blank", "only_total_cost_blank", "only_market_value_blank"],
    )
    def test_save_with_blank_cost_or_value_when_no_record_is_rejected(
        self, record_repo, total_cost, market_value
    ):
        at = _run_app(record_repo=record_repo, holding_id=_STOCK_ID)
        assert at.text_input(key="cost_basis_total_cost").value == ""
        assert at.text_input(key="cost_basis_market_value").value == ""
        if total_cost:
            at.text_input(key="cost_basis_total_cost").set_value(total_cost).run()
        if market_value:
            at.text_input(key="cost_basis_market_value").set_value(market_value).run()
        _click(at, "儲存此列")

        assert record_repo.batch_upserted == []
        assert at.error

    @pytest.mark.scenario("SC-090")
    def test_two_fields_sum_into_preview_and_saved_record(self, record_repo):
        at = _run_app(today=date(2026, 6, 15), record_repo=record_repo, holding_id=_STOCK_ID)
        at.text_input(key="cost_basis_total_cost").set_value("0").run()
        at.text_input(key="cost_basis_market_value").set_value("0").run()
        at.text_input(key="cost_basis_realized_pnl").set_value("100000").run()
        at.text_input(key="cost_basis_cash_dividend").set_value("2000").run()
        # 前期總成本＝初始成本 300000；(0−300000)−(100000+2000)＝−402000
        assert "推算本月淨投入：-402,000" in _all_written_text(at)

        _click(at, "儲存此列")
        saved = record_repo.batch_upserted[0]
        assert saved.realized_income == 102000.0
        assert saved.cash_dividend == 2000.0
        assert saved.net_investment == -402000.0

    @pytest.mark.scenario("SC-091")
    def test_negative_dividend_rejected_in_preview_and_on_save(self, record_repo):
        at = _run_app(today=date(2026, 6, 15), record_repo=record_repo, holding_id=_STOCK_ID)
        at.text_input(key="cost_basis_total_cost").set_value("0").run()
        at.text_input(key="cost_basis_market_value").set_value("0").run()
        at.text_input(key="cost_basis_realized_pnl").set_value("100000").run()
        at.text_input(key="cost_basis_cash_dividend").set_value("-1000").run()

        assert any("現金股利不可為負" in e.value for e in at.error)
        assert not any("輸入完成後顯示推算值" in c.value for c in at.caption)

        _click(at, "儲存此列")
        assert record_repo.batch_upserted == []
        assert any("現金股利不可為負" in e.value for e in at.error)

    @pytest.mark.scenario("SC-091")
    def test_zero_dividend_and_negative_pnl_are_valid(self):
        at = _run_app(today=date(2026, 6, 15), holding_id=_STOCK_ID)
        at.text_input(key="cost_basis_total_cost").set_value("0").run()
        at.text_input(key="cost_basis_realized_pnl").set_value("-5000").run()
        assert not at.error
        assert any("推算本月淨投入" in v for v in _all_written_text(at))


class TestAmountDueEditor:
    """負債：只填應繳金額，淨投入固定 0，存檔與刪除一律走批次寫入。"""

    @pytest.mark.scenario("SC-101")
    def test_existing_amount_due_is_prefilled(self, record_repo):
        record_repo.month_records["2026-05"] = [_rec(_CARD_ID, "2026-05", market_value=30000.0)]
        at = _run_app(record_repo=record_repo, holding_id=_CARD_ID)
        assert at.text_input(key="amount_due_amount").value == "30,000"

    @pytest.mark.scenario("SC-087")
    def test_no_record_leaves_amount_due_blank_and_blank_save_is_rejected(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_CARD_ID)
        assert at.text_input(key="amount_due_amount").value == ""

        _click(at, "儲存此列")

        assert record_repo.batch_upserted == []
        assert at.error

    @pytest.mark.scenario("SC-100")
    def test_save_writes_amount_due_with_zero_net_investment_via_batch(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_CARD_ID)
        at.text_input(key="amount_due_amount").set_value("30000").run()
        _click(at, "儲存此列")

        assert len(record_repo.batch_upserted) == 1
        saved = record_repo.batch_upserted[0]
        assert saved.holding_id == _CARD_ID
        assert saved.year_month == "2026-05"
        assert saved.market_value == 30000.0
        assert saved.net_investment == 0.0
        assert record_repo.upserted == []
        assert any("已儲存" in s.value for s in at.success)

    @pytest.mark.scenario("SC-100")
    def test_delete_goes_through_batch_delete_not_single_delete(self, record_repo):
        at = _run_app(record_repo=record_repo, holding_id=_CARD_ID)
        _click(at, "刪除此列")

        assert record_repo.deleted_and_upserted == [(_CARD_ID, "2026-05", [])]
        assert record_repo.deleted_single == []


class TestWriteFailureShowsFriendlyMessage:
    """寫入失敗（Repository 已復原並拋 PersistenceError）時只顯示友善訊息，輸入值保留。"""

    @staticmethod
    def _failing_repo() -> _StubRecordRepo:
        record_repo = _StubRecordRepo()
        try:
            raise RuntimeError("secret SQL detail: INSERT INTO monthly_records")
        except RuntimeError as cause:
            failure = PersistenceError()
            failure.__cause__ = cause
        record_repo.failure = failure
        return record_repo

    @pytest.mark.scenario("SC-085")
    @pytest.mark.parametrize(
        ("holding_id", "values"),
        [
            (_DEMAND_ID, {"balance_amount": "400000"}),
            (
                _INSURANCE_ID,
                {"premium_cumulative_premium": "620000", "premium_surrender_value": "585000"},
            ),
            (
                _STOCK_ID,
                {"cost_basis_total_cost": "350000", "cost_basis_market_value": "400000"},
            ),
            (_CARD_ID, {"amount_due_amount": "30000"}),
        ],
        ids=["balance", "premium", "cost_basis", "amount_due"],
    )
    def test_save_failure_shows_only_friendly_message_and_keeps_input(
        self, holding_id, values
    ):
        record_repo = self._failing_repo()
        at = _run_app(record_repo=record_repo, holding_id=holding_id)
        for key, value in values.items():
            at.text_input(key=key).set_value(value).run()
        _click(at, "儲存此列")

        assert not at.exception
        assert [e.value for e in at.error] == [_FRIENDLY_WRITE_FAILURE]
        assert "secret SQL" not in _page_text(at)
        assert not any("已儲存" in s.value for s in at.success)
        for key, value in values.items():
            assert at.text_input(key=key).value.replace(",", "") == value

    @pytest.mark.scenario("SC-085")
    @pytest.mark.parametrize(
        "holding_id",
        [_DEMAND_ID, _INSURANCE_ID, _STOCK_ID, _CARD_ID],
        ids=["balance", "premium", "cost_basis", "amount_due"],
    )
    def test_delete_failure_shows_only_friendly_message(self, holding_id):
        record_repo = self._failing_repo()
        at = _run_app(record_repo=record_repo, holding_id=holding_id)
        _click(at, "刪除此列")

        assert not at.exception
        assert [e.value for e in at.error] == [_FRIENDLY_WRITE_FAILURE]
        assert "secret SQL" not in _page_text(at)
        assert not any("已刪除" in s.value for s in at.success)

    @pytest.mark.scenario("SC-100")
    def test_liability_write_failure_uses_same_friendly_message(self):
        record_repo = self._failing_repo()
        at = _run_app(record_repo=record_repo, holding_id=_LOAN_ID)
        at.text_input(key="amount_due_amount").set_value("20000").run()
        _click(at, "儲存此列")

        assert [e.value for e in at.error] == [_FRIENDLY_WRITE_FAILURE]


class TestAmountFieldsUseEnlargedStyleContainer:
    """所有錄入金額欄都經由 amount_input，外層 container 帶放大樣式用的 key 前綴。"""

    @pytest.mark.scenario("SC-083")
    @pytest.mark.parametrize(
        ("holding_id", "labels"),
        [
            (_DEMAND_ID, {"餘額"}),
            (_INSURANCE_ID, {"累計已繳保費", "解約金", "本月領回金額"}),
            (_STOCK_ID, {"目前總成本", "現值", "本月已實現損益", "本月現金股利"}),
            (_CARD_ID, {"應繳金額"}),
        ],
        ids=["balance", "premium", "cost_basis", "amount_due"],
    )
    def test_every_amount_field_is_wrapped_by_prefixed_container(self, holding_id, labels):
        at = _run_app(holding_id=holding_id)

        wrapped: set[str] = set()

        def walk(node, inside: bool) -> None:
            node_id = getattr(getattr(node, "proto", None), "id", "") or ""
            now_inside = inside or ("amount-input-" in node_id)
            key = getattr(node, "key", None)
            if now_inside and key:
                wrapped.add(key)
            for child in (getattr(node, "children", None) or {}).values():
                walk(child, now_inside)

        walk(at.main, False)

        assert _keys(at) <= wrapped
        shown_labels = {ti.label for ti in at.text_input}
        for expected in labels:
            assert any(label.startswith(expected) for label in shown_labels), expected


class TestMonthRecordsTable:
    """本月已存紀錄表格：逐列顯示、依資產/負債拆欄、未填提醒、空狀態、存檔後即時反映。"""

    @staticmethod
    def _repo() -> _StubRecordRepo:
        record_repo = _StubRecordRepo()
        record_repo.month_records["2026-06"] = [
            _rec(_DEMAND_ID, "2026-06", market_value=370000.0, net_investment=-130000.0),
            _rec(_CARD_ID, "2026-06", market_value=30000.0),
            _rec(_LOAN_ID, "2026-06", market_value=None),
            _rec(
                _STOCK_ID,
                "2026-06",
                market_value=0.0,
                total_cost=0.0,
                realized_income=50000.0,
            ),
            _rec(_TIME_ID, "2026-06", market_value=None),
            _rec(
                _INSURANCE_ID,
                "2026-06",
                market_value=585000.0,
                total_cost=620000.0,
                realized_income=5000.0,
            ),
        ]
        return record_repo

    def _by_name(self) -> dict[str, dict]:
        at = _run_app(today=date(2026, 6, 15), record_repo=self._repo())
        rows = at.dataframe[0].value.to_dict("records")
        return {r["項目"]: r for r in rows}

    @pytest.mark.scenario("SC-101")
    def test_asset_amount_in_market_value_column_and_liability_in_amount_due_column(self):
        by_name = self._by_name()

        assert by_name["活存"]["市值 / 餘額"] == "370,000"
        assert by_name["活存"]["應繳金額"] == ""
        assert by_name["信用卡"]["應繳金額"] == "30,000"
        assert by_name["信用卡"]["市值 / 餘額"] == ""

    @pytest.mark.scenario("SC-101")
    @pytest.mark.scenario("SC-089")
    def test_reminder_text_depends_on_asset_or_liability(self):
        by_name = self._by_name()

        assert by_name["房貸"]["提醒"] == "本月應繳金額尚未填"
        assert by_name["定存"]["提醒"] == "本月市值尚未填"
        assert by_name["活存"]["提醒"] == ""
        assert by_name["信用卡"]["提醒"] == ""
        assert by_name["台積電"]["提醒"] == ""

    @pytest.mark.scenario("SC-089")
    def test_cost_columns_cover_stock_and_premium_with_new_headers(self):
        by_name = self._by_name()

        assert by_name["台積電"]["總成本 / 累計保費"] == "0"
        assert by_name["台積電"]["已實現收益 / 領回"] == "50,000"
        assert by_name["海外年金保單"]["總成本 / 累計保費"] == "620,000"
        assert by_name["海外年金保單"]["已實現收益 / 領回"] == "5,000"
        assert by_name["活存"]["淨投入"] == "-130,000"
        assert "總成本" not in by_name["活存"]
        assert "已實現收益（損益＋股利）" not in by_name["活存"]

    @pytest.mark.scenario("SC-089")
    def test_empty_month_shows_empty_state_without_reminder(self):
        at = _run_app(today=date(2026, 6, 15))
        assert len(at.dataframe) == 0
        assert any("尚無" in c.value for c in at.caption)

    @pytest.mark.scenario("SC-089")
    def test_table_reflects_saved_record_immediately(self, record_repo):
        def _save(*, records):
            for record in records:
                record_repo.month_records.setdefault(record.year_month, []).append(record)

        record_repo.upsert_records = _save
        at = _run_app(today=date(2026, 6, 15), record_repo=record_repo)
        assert len(at.dataframe) == 0
        at.text_input(key="balance_amount").set_value("370000").run()
        _click(at, "儲存此列")

        assert len(at.dataframe) == 1
        assert any("已儲存" in s.value for s in at.success)

    @pytest.mark.scenario("SC-089")
    @pytest.mark.scenario("SC-101")
    def test_liability_reminder_disappears_after_saving_amount_due(self, record_repo):
        record_repo.month_records["2026-06"] = [_rec(_LOAN_ID, "2026-06", market_value=None)]

        def _save(*, records):
            record_repo.month_records["2026-06"] = list(records)

        record_repo.upsert_records = _save
        at = _run_app(today=date(2026, 6, 15), record_repo=record_repo, holding_id=_LOAN_ID)
        before = at.dataframe[0].value.to_dict("records")[0]
        assert before["提醒"] == "本月應繳金額尚未填"

        at.text_input(key="amount_due_amount").set_value("28000").run()
        _click(at, "儲存此列")

        after = at.dataframe[0].value.to_dict("records")[0]
        assert after["應繳金額"] == "28,000"
        assert after["提醒"] == ""
