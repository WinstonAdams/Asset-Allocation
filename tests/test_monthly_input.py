# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.services.monthly_input_service import MonthlyInputService


class _StubRecordRepo:
    """記錄層替身：以固定的「最新月份」與「逐月紀錄」餵入帶入邏輯，不觸真實 I/O。"""

    def __init__(
        self,
        *,
        latest_ym: str | None,
        records_by_month: dict[str, list[MonthlyRecordModel]] | None = None,
    ) -> None:
        self._latest_ym = latest_ym
        self._records_by_month = records_by_month or {}

    def latest_year_month(self) -> str | None:
        return self._latest_ym

    def read_month(self, *, year_month: str) -> list[MonthlyRecordModel]:
        return list(self._records_by_month.get(year_month, []))


class _StubHoldingRepo:
    """主檔層替身：首月無上月可帶時，由此提供待挑選的項目主檔。"""

    def __init__(self, *, holdings: list[HoldingModel] | None = None) -> None:
        self._holdings = holdings or []

    def list_holdings(self) -> list[HoldingModel]:
        return list(self._holdings)


def _asset(holding_id: int, name: str) -> HoldingModel:
    """建立一個資產項目主檔（帶入/轉移運算不依賴初始市值/成本）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=name,
        kind=HOLDING_KIND.ASSET,
        category=ASSET_CATEGORIES.TW_STOCK,
        initial_market_value=0.0,
        initial_cost=0.0,
    )


def _liability(holding_id: int, name: str) -> HoldingModel:
    """建立一個負債項目主檔（kind=liability，category/initial_* 皆 None）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=name,
        kind=HOLDING_KIND.LIABILITY,
        category=None,
        initial_market_value=None,
        initial_cost=None,
    )


def _prev_record(
    holding_id: int, year_month: str, market_value: float | None, net_investment: float = 0.0
) -> MonthlyRecordModel:
    """建立上月某項目的紀錄，供帶入邏輯判斷是否仍持有。"""
    return MonthlyRecordModel(
        holding_id=holding_id,
        year_month=year_month,
        market_value=market_value,
        net_investment=net_investment,
    )


def _service(record_repo, holding_repo=None) -> MonthlyInputService:
    """以替身組裝 MonthlyInputService（建構子依 keyword args 注入兩個 repo）。"""
    return MonthlyInputService(
        holding_repo=holding_repo or _StubHoldingRepo(),
        record_repo=record_repo,
    )


class TestPrefillFromPrevious:
    """prefill_from_previous：新增月份自動帶入上月仍持有清單 —— SC-005 / SC-009。"""

    @pytest.mark.scenario("SC-005")
    def test_sc005_carries_previous_month_still_held_items(self):
        # 上月（2026-04）記錄三個仍持有的項目，新增 2026-05 自動帶入這三項
        prev_records = [
            _prev_record(1, "2026-04", 530000.0),
            _prev_record(2, "2026-04", 470000.0),
            _prev_record(3, "2026-04", 120000.0),
        ]
        repo = _StubRecordRepo(latest_ym="2026-04", records_by_month={"2026-04": prev_records})
        prefilled = _service(repo).prefill_from_previous(target_ym="2026-05")
        # 三個仍持有項目皆帶入新月份
        assert {record.holding_id for record in prefilled} == {1, 2, 3}
        assert all(record.year_month == "2026-05" for record in prefilled)

    @pytest.mark.scenario("SC-005")
    def test_sc005_prefilled_market_value_blank_net_investment_zero(self):
        # 帶入的市值欄留空待輸入、淨投入欄預設為 0（即使上月有淨投入也不沿用）
        prev_records = [_prev_record(1, "2026-04", 530000.0, net_investment=50000.0)]
        repo = _StubRecordRepo(latest_ym="2026-04", records_by_month={"2026-04": prev_records})
        prefilled = _service(repo).prefill_from_previous(target_ym="2026-05")
        assert len(prefilled) == 1
        assert prefilled[0].market_value is None
        assert prefilled[0].net_investment == 0.0

    @pytest.mark.scenario("SC-005")
    def test_sc005_first_month_falls_back_to_holdings_master(self):
        # 首月無上月可帶（latest_year_month 為 None）：改由主檔挑選項目
        record_repo = _StubRecordRepo(latest_ym=None)
        holding_repo = _StubHoldingRepo(holdings=[_asset(1, "台積電"), _asset(2, "現金")])
        prefilled = _service(record_repo, holding_repo).prefill_from_previous(target_ym="2026-01")
        # 主檔兩項皆列入，年月為目標月、市值留空、淨投入 0
        assert {record.holding_id for record in prefilled} == {1, 2}
        assert all(record.year_month == "2026-01" for record in prefilled)
        assert all(record.market_value is None for record in prefilled)
        assert all(record.net_investment == 0.0 for record in prefilled)

    @pytest.mark.scenario("SC-005")
    def test_sc005_first_month_empty_master_yields_empty(self):
        # 首月且主檔尚無任何項目：無可帶入清單
        record_repo = _StubRecordRepo(latest_ym=None)
        holding_repo = _StubHoldingRepo(holdings=[])
        prefilled = _service(record_repo, holding_repo).prefill_from_previous(target_ym="2026-01")
        assert prefilled == []

    @pytest.mark.scenario("SC-005")
    def test_sc005_carries_liability_items_too(self):
        # 仍持有清單不分資產負債：上月有餘額的負債（如房貸）同樣帶入新月份
        prev_records = [
            _prev_record(1, "2026-04", 530000.0),
            _prev_record(9, "2026-04", 8000000.0),
        ]
        repo = _StubRecordRepo(latest_ym="2026-04", records_by_month={"2026-04": prev_records})
        prefilled = _service(repo).prefill_from_previous(target_ym="2026-05")
        assert {record.holding_id for record in prefilled} == {1, 9}

    @pytest.mark.scenario("SC-005")
    @pytest.mark.scenario("SC-009")
    def test_sc005_sold_item_not_carried(self):
        # 上月已賣出（市值 0 = 出清，AD-10）的項目不帶入新月份；仍持有的照常帶入
        prev_records = [
            _prev_record(1, "2026-05", 0.0, net_investment=-530000.0),  # 台積電全數賣出
            _prev_record(2, "2026-05", 470000.0),  # 現金仍持有
        ]
        repo = _StubRecordRepo(latest_ym="2026-05", records_by_month={"2026-05": prev_records})
        prefilled = _service(repo).prefill_from_previous(target_ym="2026-06")
        # 已賣出的台積電不帶入；只帶入仍持有的現金
        assert {record.holding_id for record in prefilled} == {2}

    @pytest.mark.scenario("SC-005")
    def test_sc005_blank_market_value_previous_still_carried(self):
        # 上月列出但市值留空（仍持有、當月未更新市值）：仍視為持有，照常帶入
        prev_records = [_prev_record(1, "2026-04", None)]
        repo = _StubRecordRepo(latest_ym="2026-04", records_by_month={"2026-04": prev_records})
        prefilled = _service(repo).prefill_from_previous(target_ym="2026-05")
        assert {record.holding_id for record in prefilled} == {1}


class TestPrefillSoldExclusion:
    """SC-009：賣出當月記市值 0、之後缺列，後續月份不再帶入該項目。"""

    @pytest.mark.scenario("SC-009")
    def test_sc009_sale_month_zero_value_negative_net_investment_recorded(self):
        # 賣出當月（2026-05）以市值 0、淨投入 −530000 記錄，捕捉最後一期報酬與資金流出
        record = _prev_record(1, "2026-05", 0.0, net_investment=-530000.0)
        # 賣出當月本身仍是一筆有效紀錄（出清語意），不是空列
        assert record.market_value == 0.0
        assert record.net_investment == -530000.0

    @pytest.mark.scenario("SC-009")
    def test_sc009_no_carry_after_sale_month(self):
        # 自賣出之後的月份起不再帶入該已賣出項目（缺列＝已不持有）
        prev_records = [_prev_record(1, "2026-05", 0.0, net_investment=-530000.0)]
        repo = _StubRecordRepo(latest_ym="2026-05", records_by_month={"2026-05": prev_records})
        prefilled = _service(repo).prefill_from_previous(target_ym="2026-06")
        # 整個清單為空：唯一項目已出清，不續記市值 0 的空列
        assert prefilled == []


class TestBuildTransferPair:
    """build_transfer_pair：項目間轉移成對記錄淨投入 —— SC-008。"""

    @pytest.mark.scenario("SC-008")
    def test_sc008_pair_records_opposite_net_investments(self):
        # 2026-05 把 50000 從現金（id=2）轉到台積電（id=1）
        source, dest = _service(_StubRecordRepo(latest_ym="2026-05")).build_transfer_pair(
            source_id=2, dest_id=1, amount=50000.0, year_month="2026-05"
        )
        # 來源記 −50000、目標記 +50000
        assert source.holding_id == 2
        assert source.net_investment == -50000.0
        assert dest.holding_id == 1
        assert dest.net_investment == 50000.0

    @pytest.mark.scenario("SC-008")
    def test_sc008_pair_same_month_and_equal_opposite_amounts(self):
        # 兩筆同月份、金額相等、方向相反
        source, dest = _service(_StubRecordRepo(latest_ym="2026-05")).build_transfer_pair(
            source_id=2, dest_id=1, amount=50000.0, year_month="2026-05"
        )
        assert source.year_month == dest.year_month == "2026-05"
        assert source.net_investment == -dest.net_investment

    @pytest.mark.scenario("SC-008")
    def test_sc008_transfer_keeps_total_net_investment_zero(self):
        # 轉移本身不改變整體：成對淨投入合計為 0（資金只是在資產間移動）
        source, dest = _service(_StubRecordRepo(latest_ym="2026-05")).build_transfer_pair(
            source_id=2, dest_id=1, amount=50000.0, year_month="2026-05"
        )
        assert source.net_investment + dest.net_investment == 0.0

    @pytest.mark.scenario("SC-008")
    def test_sc008_transfer_pair_market_value_left_blank(self):
        # 轉移只記淨投入流動，不直接設定市值（市值由當月市值更新另行輸入）
        source, dest = _service(_StubRecordRepo(latest_ym="2026-05")).build_transfer_pair(
            source_id=2, dest_id=1, amount=50000.0, year_month="2026-05"
        )
        assert source.market_value is None
        assert dest.market_value is None


class TestTransferInputGuard:
    """SC-037：項目間轉移的輸入防呆。

    轉移金額須為正數、來源與目標須為不同項目；違反任一條件即拒絕並拋
    DataValidationError，不產生任何紀錄。
    """

    @pytest.mark.scenario("SC-037")
    def test_sc037_zero_amount_rejected(self):
        # 金額為 0（無資金移動）：拒絕並拋錯，不產生紀錄
        service = _service(_StubRecordRepo(latest_ym="2026-05"))
        with pytest.raises(DataValidationError):
            service.build_transfer_pair(
                source_id=2, dest_id=1, amount=0.0, year_month="2026-05"
            )

    @pytest.mark.scenario("SC-037")
    def test_sc037_negative_amount_rejected(self):
        # 金額為負（方向不明）：拒絕並拋錯，不產生紀錄
        service = _service(_StubRecordRepo(latest_ym="2026-05"))
        with pytest.raises(DataValidationError):
            service.build_transfer_pair(
                source_id=2, dest_id=1, amount=-50000.0, year_month="2026-05"
            )

    @pytest.mark.scenario("SC-037")
    def test_sc037_same_source_and_dest_rejected(self):
        # 來源等於目標（自己轉自己，淨效果為 0）：拒絕並拋錯，不產生紀錄
        service = _service(_StubRecordRepo(latest_ym="2026-05"))
        with pytest.raises(DataValidationError):
            service.build_transfer_pair(
                source_id=1, dest_id=1, amount=50000.0, year_month="2026-05"
            )

    @pytest.mark.scenario("SC-037")
    def test_sc037_positive_amount_distinct_items_allowed(self):
        # 金額為正且來源≠目標：通過防呆，照常產生成對紀錄
        source, dest = _service(_StubRecordRepo(latest_ym="2026-05")).build_transfer_pair(
            source_id=2, dest_id=1, amount=50000.0, year_month="2026-05"
        )
        assert source.net_investment == -50000.0
        assert dest.net_investment == 50000.0
