"""月度錄入頁年月下拉選擇器與股票/ETF 總成本整合的行為測試。

背景：views/input.py 原以 st.text_input 讓使用者自由輸入 'YYYY-MM' 字串；改為年+月兩個
st.selectbox，預設帶入當月（依 Asia/Taipei 時區判定）。產出值仍為既有下游服務消費的
'YYYY-MM' 字串，不改變 MonthlyInputService 介面或其帶入/轉移邏輯本身（那些已由
test_monthly_input.py 的 SC-005/008/009/037 測試覆蓋）。前半段（年月下拉）純 UI 機制，
無新業務語義，不掛 SC marker。

後半段新增股票/ETF 總成本輸入的整合測試：分類判斷、推算預覽、存檔/刪除委派、轉移端
過濾，這些業務規則本身已由 Service 層測試覆蓋（SC-074~080，見 test_cost_basis.py／
test_monthly_input.py），本檔用真正的 CostBasisService（純運算、無 I/O）搭配 Repository
替身，驗證 View 層的委派線路本身沒有接錯，而非重新驗證業務規則——但仍掛回對應業務規則的
SC marker（同一規則允許多個 test 從不同層次覆蓋）。

比照 test_page_config.py／test_navigation_guard.py 的做法：以 AppTest 直接載入
views/input.py（非透過 app.py 的守門與真實 Turso 容器），改以替身容器注入
session_state["container"]，並攔截 today_in_timezone 固定時鐘，脫離真實時鐘與網路依賴。
"""

# ==== 原生（標準庫） ====
from datetime import date
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, COST_BASIS_INPUT
from asset_lab.services.cost_basis_service import CostBasisService

_STOCK_CATEGORY = ASSET_CATEGORIES.TW_STOCK
_NON_STOCK_CATEGORY = ASSET_CATEGORIES.DEMAND_DEPOSIT


class _StubHoldingRepo:
    """主檔替身：固定回傳兩個項目，供轉移下拉「至少兩個項目」的畫面分支渲染。

    兩個項目皆非股票/ETF 分類，讓年月下拉相關測試維持走既有市值/淨投入輸入分支；
    股票/ETF 分支另有專屬替身（見 _StubCostBasisHoldingRepo）。
    """

    def list_holdings(self):
        return [
            SimpleNamespace(holding_id=1, name="台積電", category=_NON_STOCK_CATEGORY),
            SimpleNamespace(holding_id=2, name="現金", category=_NON_STOCK_CATEGORY),
        ]


class _StubRecordRepo:
    """記錄層替身：不觸真實 I/O，只記錄是否被呼叫。"""

    def __init__(self):
        self.upserted: list[object] = []
        self.batch_upserted: list[object] = []
        self.deleted_and_upserted: list[tuple] = []
        self.holding_records: dict[int, list[object]] = {}

    def upsert_record(self, *, record):
        self.upserted.append(record)

    def delete_record(self, *, holding_id, year_month):
        pass

    def upsert_records(self, *, records):
        self.batch_upserted.extend(records)

    def delete_record_and_upsert(self, *, holding_id, year_month, records):
        self.deleted_and_upserted.append((holding_id, year_month, records))

    def read_holding_records(self, *, holding_id):
        return self.holding_records.get(holding_id, [])


class _SpyMonthlyInputService:
    """服務替身：記錄呼叫時實際收到的 target_ym/year_month，供斷言下拉選擇正確傳遞。"""

    def __init__(self):
        self.prefill_calls: list[str] = []
        self.transfer_calls: list[tuple[int, int, float, str]] = []

    def prefill_from_previous(self, *, target_ym: str):
        self.prefill_calls.append(target_ym)
        return []

    def build_transfer_pair(self, *, source_id, dest_id, amount, year_month):
        self.transfer_calls.append((source_id, dest_id, amount, year_month))
        source = SimpleNamespace(
            holding_id=source_id, year_month=year_month, market_value=None, net_investment=-amount
        )
        dest = SimpleNamespace(
            holding_id=dest_id, year_month=year_month, market_value=None, net_investment=amount
        )
        return source, dest


def _run_app(
    *,
    today: date,
    service: _SpyMonthlyInputService,
    record_repo=None,
    holding_repo=None,
    cost_basis_service=None,
) -> AppTest:
    """以固定時鐘與替身容器跑 views/input.py，回傳已 run() 完成的 AppTest。

    cost_basis_service 預設用真正的 CostBasisService（純運算、無 I/O），讓分類判斷與
    推算走真實邏輯，測試只需要準備好替身 Repository 即可，不必另外造一個重複實作
    uses_cost_basis/derive 規則的假 Service。
    """
    container = SimpleNamespace(
        record_repo=record_repo or _StubRecordRepo(),
        holding_repo=holding_repo or _StubHoldingRepo(),
        monthly_input_service=service,
        cost_basis_service=cost_basis_service
        or CostBasisService(cost_basis_categories=COST_BASIS_INPUT.CATEGORIES),
    )
    with mock.patch("asset_lab.services.period_service.today_in_timezone", return_value=today):
        at = AppTest.from_file("views/input.py")
        at.session_state["container"] = container
        at.run()
    return at


def _all_written_text(at: AppTest) -> set[str]:
    """彙總 st.write 輸出的 markdown 文字，供斷言預覽內容用。"""
    return {m.value for m in at.markdown}


class TestDefaultMonthDropdown:
    """年+月下拉預設帶入當月，且依 Asia/Taipei 時區判定（由呼叫端注入的固定日期驗證）。"""

    def test_default_selectboxes_show_current_month_in_timezone(self):
        at = _run_app(today=date(2026, 3, 15), service=_SpyMonthlyInputService())
        assert not at.exception
        assert at.selectbox(key="input_target_year").value == 2026
        assert at.selectbox(key="input_target_month").value == 3

    def test_default_selectboxes_cross_year_boundary(self):
        # 時區換算後已跨年（如台北已進入新年 1/1）：預設應落在新年份的 1 月
        at = _run_app(today=date(2026, 1, 1), service=_SpyMonthlyInputService())
        assert at.selectbox(key="input_target_year").value == 2026
        assert at.selectbox(key="input_target_month").value == 1

    def test_default_selectboxes_end_of_year(self):
        at = _run_app(today=date(2025, 12, 31), service=_SpyMonthlyInputService())
        assert at.selectbox(key="input_target_year").value == 2025
        assert at.selectbox(key="input_target_month").value == 12


class TestYearDropdownBounded:
    """年份下拉為當年往前推固定年數的有界範圍，不含未來年份。"""

    def test_year_options_bounded_around_current_year(self):
        at = _run_app(today=date(2026, 6, 1), service=_SpyMonthlyInputService())
        year_select = at.selectbox(key="input_target_year")
        assert year_select.options == [str(y) for y in range(2021, 2027)]

    def test_month_options_cover_all_twelve_months(self):
        at = _run_app(today=date(2026, 6, 1), service=_SpyMonthlyInputService())
        month_select = at.selectbox(key="input_target_month")
        assert month_select.options == [f"{m:02d}" for m in range(1, 13)]


class TestSelectedMonthPassedDownstream:
    """使用者變更年月下拉後，選定值（非預設當月）正確組成 'YYYY-MM' 傳給既有下游服務呼叫。

    帶入/轉移的業務邏輯本身（SC-005/008/009/037）不在此重驗，只驗證這層 UI 到 Service
    呼叫邊界的資料傳遞沒有被下拉改版破壞。
    """

    def test_prefill_button_passes_selected_year_month(self):
        service = _SpyMonthlyInputService()
        at = _run_app(today=date(2026, 3, 15), service=service)
        at.selectbox(key="input_target_year").set_value(2024)
        at.selectbox(key="input_target_month").set_value(11)
        prefill_button = next(b for b in at.button if b.label == "帶入上月仍持有項目")
        prefill_button.click().run()
        assert service.prefill_calls[-1] == "2024-11"

    def test_transfer_button_passes_selected_year_month(self):
        service = _SpyMonthlyInputService()
        record_repo = _StubRecordRepo()
        at = _run_app(today=date(2026, 3, 15), service=service, record_repo=record_repo)
        at.selectbox(key="input_target_year").set_value(2025)
        at.selectbox(key="input_target_month").set_value(7)
        at.text_input(key="amt").set_value("1000")
        transfer_button = next(b for b in at.button if b.label == "建立轉移")
        transfer_button.click().run()
        assert service.transfer_calls[-1][3] == "2025-07"
        # 成對紀錄確實委派 Repository 寫入（不因下拉改版而漏寫）；兩端皆非股票/ETF，
        # transfer_records_to_write 不濾掉任何一端
        assert len(record_repo.batch_upserted) == 2


class _StubCostBasisHoldingRepo:
    """主檔替身：一個股票/ETF 項目＋一個非股票項目，供分流測試切換選定項目。

    holding_id 10 為股票/ETF（uses_cost_basis 為 True），20 為現金（False）；股票項目的
    initial_cost 用於 derive 在無任何前期紀錄時的前期總成本基準。
    """

    def list_holdings(self):
        return [
            SimpleNamespace(
                holding_id=10, name="台積電", category=_STOCK_CATEGORY, initial_cost=300000.0
            ),
            SimpleNamespace(
                holding_id=20, name="現金", category=_NON_STOCK_CATEGORY, initial_cost=None
            ),
        ]


class TestRecordEditorSwitchesFieldsByCategory:
    """單列錄入依項目分類切換欄位：股票/ETF 走總成本輸入，其餘分類走市值/淨投入。"""

    @pytest.mark.scenario("SC-074")
    def test_stock_holding_shows_cost_basis_fields(self):
        at = _run_app(
            today=date(2026, 5, 15),
            service=_SpyMonthlyInputService(),
            holding_repo=_StubCostBasisHoldingRepo(),
        )
        keys = {ti.key for ti in at.text_input}
        expected_keys = {
            "cost_basis_total_cost",
            "cost_basis_market_value",
            "cost_basis_realized_income",
        }
        assert expected_keys <= keys
        assert "record_market_value" not in keys
        assert "record_net_investment" not in keys

    @pytest.mark.scenario("SC-074")
    def test_non_stock_holding_shows_market_value_fields(self):
        at = _run_app(
            today=date(2026, 5, 15),
            service=_SpyMonthlyInputService(),
            holding_repo=_StubCostBasisHoldingRepo(),
        )
        holding_select = next(sb for sb in at.selectbox if sb.label == "項目")
        holding_select.set_value(20).run()

        keys = {ti.key for ti in at.text_input}
        assert {"record_market_value", "record_net_investment"} <= keys
        assert "cost_basis_total_cost" not in keys


class TestCostBasisPreviewAndDelegation:
    """股票/ETF 項目的存檔前預覽、儲存與刪除，正確委派 CostBasisService／Repository。

    推算數學本身（前期總成本、過渡估算、連動重算）已由 test_cost_basis.py 的
    SC-074~078 覆蓋；這裡驗證的是 View 把使用者輸入、Service 呼叫與 Repository
    寫入串起來的線路沒有接錯。
    """

    @pytest.mark.scenario("SC-074")
    def test_preview_shows_previous_total_cost_and_derived_investment(self):
        # 預設欄位皆為 0：無任何前期紀錄，前期總成本＝初始成本 300000；
        # 推算淨投入＝(0−300000)−0＝−300000
        at = _run_app(
            today=date(2026, 5, 15),
            service=_SpyMonthlyInputService(),
            holding_repo=_StubCostBasisHoldingRepo(),
        )
        written = _all_written_text(at)
        assert "前期總成本：300,000" in written
        assert "推算本月淨投入：-300,000" in written

    @pytest.mark.scenario("SC-074")
    def test_incomplete_input_shows_placeholder_instead_of_crashing(self):
        at = _run_app(
            today=date(2026, 5, 15),
            service=_SpyMonthlyInputService(),
            holding_repo=_StubCostBasisHoldingRepo(),
        )
        at.text_input(key="cost_basis_total_cost").set_value("").run()

        assert not at.exception
        assert any("輸入完成後顯示推算值" in c.value for c in at.caption)

    @pytest.mark.scenario("SC-074")
    def test_save_button_delegates_to_plan_save_then_batch_upsert(self):
        record_repo = _StubRecordRepo()
        at = _run_app(
            today=date(2026, 5, 15),
            service=_SpyMonthlyInputService(),
            holding_repo=_StubCostBasisHoldingRepo(),
            record_repo=record_repo,
        )
        at.text_input(key="cost_basis_total_cost").set_value("350000").run()
        at.text_input(key="cost_basis_market_value").set_value("400000").run()
        save_button = next(b for b in at.button if b.label == "儲存此列")
        save_button.click().run()

        assert len(record_repo.batch_upserted) == 1
        saved = record_repo.batch_upserted[0]
        assert saved.holding_id == 10
        assert saved.year_month == "2026-05"
        assert saved.total_cost == 350000.0
        assert saved.market_value == 400000.0
        assert saved.net_investment == 50000.0

    @pytest.mark.scenario("SC-077")
    def test_delete_button_delegates_to_plan_delete_then_delete_record_and_upsert(self):
        record_repo = _StubRecordRepo()
        at = _run_app(
            today=date(2026, 5, 15),
            service=_SpyMonthlyInputService(),
            holding_repo=_StubCostBasisHoldingRepo(),
            record_repo=record_repo,
        )
        delete_button = next(b for b in at.button if b.label == "刪除此列")
        delete_button.click().run()

        assert len(record_repo.deleted_and_upserted) == 1
        holding_id, year_month, plan = record_repo.deleted_and_upserted[0]
        assert holding_id == 10
        assert year_month == "2026-05"
        assert plan == []


class TestTransferFiltersCostBasisEnd:
    """項目間轉移涉及股票/ETF 端時，View 正確委派 transfer_records_to_write 濾掉該端。

    過濾規則本身（含兩端皆股票/ETF 的合法空清單情況）已由 test_monthly_input.py 的
    SC-079/SC-080 覆蓋；這裡驗證 View 有把過濾結果接上 Repository 寫入與畫面提示。
    """

    @pytest.mark.scenario("SC-079")
    def test_transfer_involving_stock_end_writes_only_non_stock_leg(self):
        service = _SpyMonthlyInputService()
        record_repo = _StubRecordRepo()
        at = _run_app(
            today=date(2026, 5, 15),
            service=service,
            holding_repo=_StubCostBasisHoldingRepo(),
            record_repo=record_repo,
        )
        at.selectbox(key="src").set_value(20)
        at.selectbox(key="dst").set_value(10)
        at.text_input(key="amt").set_value("80000")
        transfer_button = next(b for b in at.button if b.label == "建立轉移")
        transfer_button.click().run()

        assert len(record_repo.batch_upserted) == 1
        written = record_repo.batch_upserted[0]
        assert written.holding_id == 20
        assert written.net_investment == -80000.0
        assert any("已建立成對轉移紀錄" in s.value for s in at.success)

    @pytest.mark.scenario("SC-080")
    def test_transfer_both_ends_stock_writes_nothing_and_shows_info(self):
        service = _SpyMonthlyInputService()
        record_repo = _StubRecordRepo()

        class _BothStockHoldingRepo:
            def list_holdings(self):
                return [
                    SimpleNamespace(
                        holding_id=10, name="台積電", category=_STOCK_CATEGORY, initial_cost=0.0
                    ),
                    SimpleNamespace(
                        holding_id=11, name="聯發科", category=_STOCK_CATEGORY, initial_cost=0.0
                    ),
                ]

        at = _run_app(
            today=date(2026, 5, 15),
            service=service,
            holding_repo=_BothStockHoldingRepo(),
            record_repo=record_repo,
        )
        at.selectbox(key="src").set_value(10)
        at.selectbox(key="dst").set_value(11)
        at.text_input(key="amt").set_value("60000")
        transfer_button = next(b for b in at.button if b.label == "建立轉移")
        transfer_button.click().run()

        assert record_repo.batch_upserted == []
        assert any("未寫入任何紀錄" in i.value for i in at.info)
