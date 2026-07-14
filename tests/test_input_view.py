"""月度錄入頁年月下拉選擇器的行為測試（純 UI 機制，無新業務語義，不掛 SC marker）。

背景：views/input.py 原以 st.text_input 讓使用者自由輸入 'YYYY-MM' 字串；改為年+月兩個
st.selectbox，預設帶入當月（依 Asia/Taipei 時區判定）。產出值仍為既有下游服務消費的
'YYYY-MM' 字串，不改變 MonthlyInputService 介面或其帶入/轉移邏輯本身（那些已由
test_monthly_input.py 的 SC-005/008/009/037 測試覆蓋）。本檔只驗證這層 UI 機制：預設值
正確（含跨年邊界）、年份選單有界、使用者選定的年月正確傳給下游委派呼叫。

比照 test_page_config.py／test_navigation_guard.py 的做法：以 AppTest 直接載入
views/input.py（非透過 app.py 的守門與真實 Turso 容器），改以替身容器注入
session_state["container"]，並攔截 today_in_timezone 固定時鐘，脫離真實時鐘與網路依賴。
"""

# ==== 原生（標準庫） ====
from datetime import date
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
# 無


class _StubHoldingRepo:
    """主檔替身：固定回傳兩個項目，供轉移下拉「至少兩個項目」的畫面分支渲染。"""

    def list_holdings(self):
        return [
            SimpleNamespace(holding_id=1, name="台積電"),
            SimpleNamespace(holding_id=2, name="現金"),
        ]


class _StubRecordRepo:
    """記錄層替身：不觸真實 I/O，只記錄是否被呼叫。"""

    def __init__(self):
        self.upserted: list[object] = []

    def upsert_record(self, *, record):
        self.upserted.append(record)

    def delete_record(self, *, holding_id, year_month):
        pass


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


def _run_app(*, today: date, service: _SpyMonthlyInputService, record_repo=None) -> AppTest:
    """以固定時鐘與替身容器跑 views/input.py，回傳已 run() 完成的 AppTest。"""
    container = SimpleNamespace(
        record_repo=record_repo or _StubRecordRepo(),
        holding_repo=_StubHoldingRepo(),
        monthly_input_service=service,
    )
    with mock.patch("asset_lab.services.period_service.today_in_timezone", return_value=today):
        at = AppTest.from_file("views/input.py")
        at.session_state["container"] = container
        at.run()
    return at


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
        at.number_input(key="amt").set_value(1000.0)
        transfer_button = next(b for b in at.button if b.label == "建立轉移")
        transfer_button.click().run()
        assert service.transfer_calls[-1][3] == "2025-07"
        # 成對紀錄確實委派 Repository 寫入（不因下拉改版而漏寫）
        assert len(record_repo.upserted) == 2
