# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import libsql
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND
from asset_lab.core.exceptions import DataValidationError, PersistenceError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository
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
        # 上月已賣出（市值 0 = 出清）的項目不帶入新月份；仍持有的照常帶入
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


# === Repository 層月度紀錄單列 CRUD I/O（記憶體 DB，不連遠端 Turso）===


@pytest.fixture
def conn():
    """每個 test 一個獨立記憶體 DB，建好三表後交給 Repository。"""
    connection = libsql.connect(":memory:")
    SchemaRepository(conn=connection).ensure_schema()
    yield connection


@pytest.fixture
def record_repo(conn):
    return RecordRepository(conn=conn)


@pytest.fixture
def seeded_holding_id(conn):
    """先在主檔建一個資產項目，回傳其 holding_id 供月度紀錄掛載。"""
    return HoldingRepository(conn=conn).add_holding(
        holding=HoldingModel(
            holding_id=None,
            name="台積電",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_market_value=500000.0,
            initial_cost=300000.0,
        )
    )


def _record(
    holding_id: int,
    year_month: str,
    market_value: float,
    net_investment: float = 0.0,
    *,
    total_cost: float | None = None,
    realized_income: float | None = None,
):
    return MonthlyRecordModel(
        holding_id=holding_id,
        year_month=year_month,
        market_value=market_value,
        net_investment=net_investment,
        total_cost=total_cost,
        realized_income=realized_income,
    )


class TestSaleMonthClearoutPersisted:
    """SC-009：賣出當月以市值 0、負淨投入記錄，是一筆真實持久化的有效紀錄（非空列）。"""

    @pytest.mark.scenario("SC-009")
    def test_sc009_sale_month_zero_value_negative_net_investment_persisted(
        self, record_repo, seeded_holding_id
    ):
        # 賣出當月（2026-05）取回 530000：以市值 0、淨投入 −530000 寫入儲存層
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 0.0, -530000.0)
        )
        # 讀回確認：賣出當月被持久化為一筆有效紀錄（捕捉最後一期報酬與資金流出），非缺列
        month = record_repo.read_month(year_month="2026-05")
        assert len(month) == 1
        assert month[0].holding_id == seeded_holding_id
        assert month[0].market_value == 0.0
        assert month[0].net_investment == -530000.0

    @pytest.mark.scenario("SC-009")
    def test_sc009_sale_month_value_captured_in_return_input_series(
        self, record_repo, seeded_holding_id
    ):
        # 賣出當月的市值 0／淨投入 −530000 確實進入下游報酬連乘的輸入序列（read_range）
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-04", 530000.0, 0.0)
        )
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 0.0, -530000.0)
        )
        history = record_repo.read_range(start_ym="2026-04", end_ym="2026-05")
        # 兩個月皆為有值節點，賣出當月不被當成空列略過
        by_month = dict(zip(history["year_month"], history["market_value"], strict=True))
        assert by_month["2026-05"] == 0.0
        nets = dict(zip(history["year_month"], history["net_investment"], strict=True))
        assert nets["2026-05"] == -530000.0


class TestMonthlyRecordCrud:
    """SC-006：新增/編輯/刪除某月單一項目紀錄（upsert/delete）。"""

    @pytest.mark.scenario("SC-006")
    def test_sc006_insert_single_record(self, record_repo, seeded_holding_id):
        # 新增一列：2026-05 市值 520000、淨投入 0
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0)
        )
        month = record_repo.read_month(year_month="2026-05")
        assert len(month) == 1
        assert month[0].holding_id == seeded_holding_id
        assert month[0].market_value == 520000.0
        assert month[0].net_investment == 0.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_edit_updates_in_place_without_duplicate(self, record_repo, seeded_holding_id):
        # 先新增 520000，再編輯為 530000：同一 (月,項目) 被更新，不新增重複列
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0)
        )
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 530000.0, 0.0)
        )
        month = record_repo.read_month(year_month="2026-05")
        assert len(month) == 1
        assert month[0].market_value == 530000.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_delete_removes_the_record(self, record_repo, seeded_holding_id):
        # 刪除該列後，該 (月,項目) 紀錄不再存在
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0)
        )
        record_repo.delete_record(holding_id=seeded_holding_id, year_month="2026-05")
        assert record_repo.read_month(year_month="2026-05") == []

    @pytest.mark.scenario("SC-006")
    def test_sc006_edit_does_not_touch_other_month(self, record_repo, seeded_holding_id):
        # 編輯 2026-05 不影響同項目的其他月份（2026-04）
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-04", 500000.0, 0.0)
        )
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0)
        )
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 530000.0, 0.0)
        )
        april = record_repo.read_month(year_month="2026-04")
        assert len(april) == 1
        assert april[0].market_value == 500000.0


class TestDuplicateRecordRejected:
    """SC-007：同月同項目重複記錄須被拒絕（(holding_id, year_month) 唯一鍵）。"""

    @pytest.mark.scenario("SC-007")
    def test_sc007_strict_insert_duplicate_rejected(self, record_repo, seeded_holding_id):
        # 2026-05 已存在台積電紀錄，嚴格新增同一 (月,項目) 第二列須被拒絕並拋業務例外
        record_repo.insert_record(
            record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0)
        )
        with pytest.raises(DataValidationError):
            record_repo.insert_record(
                record=_record(seeded_holding_id, "2026-05", 999999.0, 0.0)
            )

    @pytest.mark.scenario("SC-007")
    def test_sc007_original_record_not_polluted_after_rejection(
        self, record_repo, seeded_holding_id
    ):
        # 重複新增被拒後，原有 2026-05 台積電紀錄（520000）不被污染、仍僅一列
        record_repo.insert_record(
            record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0)
        )
        with pytest.raises(DataValidationError):
            record_repo.insert_record(
                record=_record(seeded_holding_id, "2026-05", 999999.0, 0.0)
            )
        month = record_repo.read_month(year_month="2026-05")
        assert len(month) == 1
        assert month[0].market_value == 520000.0

    @pytest.mark.scenario("SC-007")
    def test_sc007_unique_key_is_per_holding_per_month(self, record_repo, conn, seeded_holding_id):
        # 唯一鍵是 (項目, 月) 複合鍵：不同項目可在同月各記一列，互不衝突
        other_id = HoldingRepository(conn=conn).add_holding(
            holding=HoldingModel(
                holding_id=None,
                name="0050",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TW_STOCK,
                initial_market_value=200000.0,
                initial_cost=200000.0,
            )
        )
        record_repo.insert_record(
            record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0)
        )
        record_repo.insert_record(record=_record(other_id, "2026-05", 200000.0, 0.0))
        assert len(record_repo.read_month(year_month="2026-05")) == 2


class TestRecordRepositoryEmptyAndIdempotency:
    """月度紀錄 Repository 的空集合與重複呼叫邊界（SC-006/SC-007 的實作邊界）。"""

    @pytest.mark.scenario("SC-006")
    def test_ensure_schema_is_idempotent(self, conn):
        # 重複建表安全：再次 ensure_schema 不報錯、既有紀錄不受影響
        repo = RecordRepository(conn=conn)
        seeded = HoldingRepository(conn=conn).add_holding(
            holding=HoldingModel(
                holding_id=None,
                name="台積電",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TW_STOCK,
                initial_market_value=500000.0,
                initial_cost=300000.0,
            )
        )
        repo.upsert_record(record=_record(seeded, "2026-05", 520000.0, 0.0))
        SchemaRepository(conn=conn).ensure_schema()
        assert len(repo.read_month(year_month="2026-05")) == 1

    @pytest.mark.scenario("SC-006")
    def test_read_month_empty_returns_empty_list(self, record_repo):
        # 該月無任何紀錄時回空清單
        assert record_repo.read_month(year_month="2026-05") == []

    @pytest.mark.scenario("SC-006")
    def test_read_range_empty_preserves_columns(self, record_repo):
        # 區間無資料仍回完整欄位的空 DataFrame（避免下游連乘因缺欄崩潰）
        empty = record_repo.read_range(start_ym="2026-01", end_ym="2026-12")
        assert len(empty) == 0
        assert list(empty.columns) == [
            "holding_id",
            "year_month",
            "market_value",
            "net_investment",
            "total_cost",
            "realized_income",
            "cash_dividend",
        ]

    @pytest.mark.scenario("SC-006")
    def test_latest_year_month_none_when_empty(self, record_repo):
        # 全無紀錄時最新月份為 None（首月帶入判斷依賴此結果）
        assert record_repo.latest_year_month() is None

    @pytest.mark.scenario("SC-006")
    def test_delete_non_existent_is_noop(self, record_repo, seeded_holding_id):
        # 刪除不存在的 (項目,月) 為無操作，不報錯也不影響其他紀錄
        record_repo.upsert_record(record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0))
        record_repo.delete_record(holding_id=999, year_month="2099-01")
        assert len(record_repo.read_month(year_month="2026-05")) == 1


# === Repository 層新增能力：讀單一項目全部紀錄、批次寫入（compound method）===
# 這些方法是後續股票/ETF 總成本推算（CostBasisService）共用的資料底座，
# 本身不含業務判斷，屬既有月度紀錄 CRUD 能力（SC-006）的機械擴充。


class TestReadHoldingRecords:
    """read_holding_records：讀單一項目的全部月度紀錄，依 year_month 由舊到新排序。"""

    @pytest.mark.scenario("SC-006")
    def test_sc006_returns_all_months_sorted_ascending_by_year_month(
        self, record_repo, seeded_holding_id
    ):
        # 寫入順序刻意打亂，讀回仍依 year_month 由舊到新排序
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-07", 420000.0, 20000.0)
        )
        record_repo.upsert_record(
            record=_record(
                seeded_holding_id, "2026-05", 400000.0, 50000.0,
                total_cost=350000.0, realized_income=0.0,
            )
        )
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-06", 410000.0, 10000.0)
        )

        records = record_repo.read_holding_records(holding_id=seeded_holding_id)

        assert [r.year_month for r in records] == ["2026-05", "2026-06", "2026-07"]
        # 新制列（total_cost 不為 None）的附加欄位隨列一併正確讀回
        assert records[0].total_cost == 350000.0
        assert records[0].realized_income == 0.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_excludes_other_holdings_records(self, record_repo, conn, seeded_holding_id):
        # 只回傳指定項目的紀錄，不含其他項目同月的紀錄
        other_id = HoldingRepository(conn=conn).add_holding(
            holding=HoldingModel(
                holding_id=None,
                name="0050",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TW_STOCK,
                initial_market_value=200000.0,
                initial_cost=200000.0,
            )
        )
        record_repo.upsert_record(record=_record(seeded_holding_id, "2026-05", 520000.0, 0.0))
        record_repo.upsert_record(record=_record(other_id, "2026-05", 200000.0, 0.0))

        records = record_repo.read_holding_records(holding_id=seeded_holding_id)

        assert len(records) == 1
        assert records[0].holding_id == seeded_holding_id

    @pytest.mark.scenario("SC-006")
    def test_sc006_empty_when_holding_has_no_records(self, record_repo, seeded_holding_id):
        assert record_repo.read_holding_records(holding_id=seeded_holding_id) == []


class TestUpsertRecordsBatch:
    """upsert_records：批次 upsert 多列，單一交易。"""

    @pytest.mark.scenario("SC-006")
    def test_sc006_writes_multiple_new_rows_in_one_call(self, record_repo, seeded_holding_id):
        record_repo.upsert_records(
            records=[
                _record(
                    seeded_holding_id, "2026-05", 400000.0, 50000.0,
                    total_cost=350000.0, realized_income=0.0,
                ),
                _record(
                    seeded_holding_id, "2026-06", 420000.0, 20000.0,
                    total_cost=370000.0, realized_income=0.0,
                ),
            ]
        )

        may = record_repo.read_month(year_month="2026-05")[0]
        june = record_repo.read_month(year_month="2026-06")[0]
        assert may.net_investment == 50000.0
        assert may.total_cost == 350000.0
        assert june.net_investment == 20000.0
        assert june.total_cost == 370000.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_updates_existing_and_inserts_new_together(
        self, record_repo, seeded_holding_id
    ):
        # 先存在一筆 2026-05；批次寫入同時更新它並新增 2026-06
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 400000.0, 50000.0)
        )

        record_repo.upsert_records(
            records=[
                _record(seeded_holding_id, "2026-05", 410000.0, 60000.0),
                _record(seeded_holding_id, "2026-06", 420000.0, 20000.0),
            ]
        )

        assert record_repo.read_month(year_month="2026-05")[0].market_value == 410000.0
        assert len(record_repo.read_month(year_month="2026-05")) == 1
        assert record_repo.read_month(year_month="2026-06")[0].market_value == 420000.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_empty_list_is_noop(self, record_repo, seeded_holding_id):
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 400000.0, 50000.0)
        )

        record_repo.upsert_records(records=[])

        assert len(record_repo.read_month(year_month="2026-05")) == 1


class TestDeleteRecordAndUpsertBatch:
    """delete_record_and_upsert：刪除單列後批次 upsert 受影響列，單一交易。"""

    @pytest.mark.scenario("SC-006")
    def test_sc006_removes_target_month_and_writes_affected_months(
        self, record_repo, seeded_holding_id
    ):
        record_repo.upsert_record(
            record=_record(
                seeded_holding_id, "2026-05", 400000.0, 50000.0,
                total_cost=350000.0, realized_income=0.0,
            )
        )
        record_repo.upsert_record(
            record=_record(
                seeded_holding_id, "2026-06", 420000.0, 20000.0,
                total_cost=370000.0, realized_income=0.0,
            )
        )

        record_repo.delete_record_and_upsert(
            holding_id=seeded_holding_id,
            year_month="2026-05",
            records=[
                _record(
                    seeded_holding_id, "2026-06", 420000.0, 70000.0,
                    total_cost=370000.0, realized_income=0.0,
                ),
            ],
        )

        assert record_repo.read_month(year_month="2026-05") == []
        assert record_repo.read_month(year_month="2026-06")[0].net_investment == 70000.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_with_empty_records_only_deletes(self, record_repo, seeded_holding_id):
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 400000.0, 50000.0)
        )

        record_repo.delete_record_and_upsert(
            holding_id=seeded_holding_id, year_month="2026-05", records=[]
        )

        assert record_repo.read_month(year_month="2026-05") == []


class _FailingCursor:
    """包一個真實 cursor：前面呼叫正常執行，第 fail_at 次 execute 起拋出例外，
    用來模擬批次寫入中途失敗（不 mock 整個連線，交易控制仍走真實 libsql rollback/commit）。
    """

    def __init__(self, real_cursor, *, fail_at: int) -> None:
        self._real_cursor = real_cursor
        self._fail_at = fail_at
        self._call_count = 0

    def execute(self, *args: object, **kwargs: object):
        self._call_count += 1
        if self._call_count == self._fail_at:
            raise RuntimeError("模擬批次寫入中途失敗")
        return self._real_cursor.execute(*args, **kwargs)

    def fetchall(self):
        return self._real_cursor.fetchall()

    def fetchone(self):
        return self._real_cursor.fetchone()


class _FailAfterNCallsConnection:
    """包一個真實連線：cursor() 回傳會在第 fail_at 次 execute 時失敗的版本，
    commit/rollback 照轉呼叫真實連線，讓交易狀態仍由真實 libsql 連線管理。
    只用來對「同一個」RecordRepository 注入批次寫入中途失敗，不影響其他經由原連線
    直接查驗結果的 Repository 實例（用於斷言 rollback 後的資料狀態）。
    """

    def __init__(self, real_conn, *, fail_at: int, rollback_fails: bool = False) -> None:
        self._real_conn = real_conn
        self._fail_at = fail_at
        self._rollback_fails = rollback_fails

    def cursor(self):
        return _FailingCursor(self._real_conn.cursor(), fail_at=self._fail_at)

    def commit(self):
        self._real_conn.commit()

    def rollback(self):
        if self._rollback_fails:
            raise RuntimeError("模擬 rollback 失敗")
        self._real_conn.rollback()


class _CommitFailingConnection:
    """包一個真實連線：execute 正常，commit 一律失敗；rollback 轉呼叫真實連線。"""

    def __init__(self, real_conn) -> None:
        self._real_conn = real_conn

    def cursor(self):
        return self._real_conn.cursor()

    def commit(self):
        raise RuntimeError("模擬 commit 失敗")

    def rollback(self):
        self._real_conn.rollback()


class TestBatchWriteRollbackOnFailure:
    """批次寫入中途失敗時，已執行的部分不留存（SC-085）。"""

    @pytest.mark.scenario("SC-085")
    def test_sc085_upsert_records_failure_rolls_back_all_writes(
        self, record_repo, conn, seeded_holding_id
    ):
        # 兩筆待寫入，第二筆 execute 時失敗：第一筆也不應該被留存
        failing_repo = RecordRepository(conn=_FailAfterNCallsConnection(conn, fail_at=2))

        with pytest.raises(PersistenceError):
            failing_repo.upsert_records(
                records=[
                    _record(seeded_holding_id, "2026-05", 400000.0, 50000.0),
                    _record(seeded_holding_id, "2026-06", 420000.0, 20000.0),
                ]
            )

        assert record_repo.read_month(year_month="2026-05") == []
        assert record_repo.read_month(year_month="2026-06") == []

    @pytest.mark.scenario("SC-085")
    def test_sc085_upsert_records_failure_raises_persistence_error_with_cause(
        self, record_repo, conn, seeded_holding_id
    ):
        # 轉成友善的 PersistenceError，原始錯誤保留在 __cause__，訊息不內插原始錯誤
        failing_repo = RecordRepository(conn=_FailAfterNCallsConnection(conn, fail_at=1))

        with pytest.raises(PersistenceError) as exc_info:
            failing_repo.upsert_records(
                records=[_record(seeded_holding_id, "2026-05", 400000.0, 50000.0)]
            )

        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert "模擬批次寫入中途失敗" in str(exc_info.value.__cause__)
        assert "模擬批次寫入中途失敗" not in str(exc_info.value)

    @pytest.mark.scenario("SC-085")
    def test_sc085_delete_record_and_upsert_failure_restores_deleted_record(
        self, record_repo, conn, seeded_holding_id
    ):
        # 既有 2026-05 紀錄；刪除＋批次 upsert 中途失敗，原本的 2026-05 紀錄應維持存在
        # （未被真的刪除）
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 400000.0, 50000.0)
        )
        # call 1 = DELETE、call 2 = 第一筆 upsert（成功）、call 3 = 第二筆 upsert（失敗）
        failing_repo = RecordRepository(conn=_FailAfterNCallsConnection(conn, fail_at=3))

        with pytest.raises(PersistenceError):
            failing_repo.delete_record_and_upsert(
                holding_id=seeded_holding_id,
                year_month="2026-05",
                records=[
                    _record(seeded_holding_id, "2026-06", 420000.0, 20000.0),
                    _record(seeded_holding_id, "2026-07", 430000.0, 10000.0),
                ],
            )

        assert record_repo.read_month(year_month="2026-05")[0].market_value == 400000.0
        assert record_repo.read_month(year_month="2026-06") == []
        assert record_repo.read_month(year_month="2026-07") == []

    @pytest.mark.scenario("SC-085")
    def test_sc085_commit_failure_rolls_back_and_raises_persistence_error(
        self, record_repo, conn, seeded_holding_id
    ):
        # 所有 execute 都成功、最後 commit 失敗：仍須 rollback，不留下已執行的寫入
        failing_repo = RecordRepository(conn=_CommitFailingConnection(conn))

        with pytest.raises(PersistenceError) as exc_info:
            failing_repo.upsert_records(
                records=[_record(seeded_holding_id, "2026-05", 400000.0, 50000.0)]
            )

        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert record_repo.read_month(year_month="2026-05") == []

    @pytest.mark.scenario("SC-085")
    def test_sc085_rollback_failure_still_raises_persistence_error(
        self, conn, seeded_holding_id
    ):
        # 復原本身也失敗：使用者仍只看到同一則友善訊息，原始錯誤在 __cause__，
        # rollback 的錯誤以 note 附在原始錯誤上供 log 使用
        failing_repo = RecordRepository(
            conn=_FailAfterNCallsConnection(conn, fail_at=1, rollback_fails=True)
        )

        with pytest.raises(PersistenceError) as exc_info:
            failing_repo.upsert_records(
                records=[_record(seeded_holding_id, "2026-05", 400000.0, 50000.0)]
            )

        assert str(exc_info.value) == PersistenceError.DEFAULT_MESSAGE
        cause = exc_info.value.__cause__
        assert isinstance(cause, RuntimeError)
        assert any("rollback" in note for note in cause.__notes__)


class TestAccumulateNetInvestments:
    """accumulate_net_investments：只累加 net_investment，其餘欄位不動。"""

    @pytest.mark.scenario("SC-086")
    def test_sc086_accumulate_on_existing_row_keeps_market_value(
        self, record_repo, seeded_holding_id
    ):
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 350000.0, 0.0)
        )

        record_repo.accumulate_net_investments(
            records=[_record(seeded_holding_id, "2026-05", 0.0, -100000.0)]
        )

        stored = record_repo.read_month(year_month="2026-05")[0]
        assert stored.market_value == 350000.0
        assert stored.net_investment == -100000.0

    @pytest.mark.scenario("SC-086")
    def test_sc086_accumulate_twice_adds_up(self, record_repo, seeded_holding_id):
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 350000.0, 0.0)
        )

        record_repo.accumulate_net_investments(
            records=[_record(seeded_holding_id, "2026-05", 0.0, -100000.0)]
        )
        record_repo.accumulate_net_investments(
            records=[_record(seeded_holding_id, "2026-05", 0.0, -50000.0)]
        )

        stored = record_repo.read_month(year_month="2026-05")[0]
        assert stored.market_value == 350000.0
        assert stored.net_investment == -150000.0

    @pytest.mark.scenario("SC-086")
    def test_sc086_accumulate_leaves_cost_columns_untouched(
        self, record_repo, seeded_holding_id
    ):
        record_repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=seeded_holding_id,
                year_month="2026-05",
                market_value=400000.0,
                net_investment=10000.0,
                total_cost=350000.0,
                realized_income=1200.0,
                cash_dividend=200.0,
            )
        )

        record_repo.accumulate_net_investments(
            records=[_record(seeded_holding_id, "2026-05", 999.0, 5000.0,
                             total_cost=1.0, realized_income=2.0)]
        )

        stored = record_repo.read_month(year_month="2026-05")[0]
        assert stored.net_investment == 15000.0
        assert stored.market_value == 400000.0
        assert stored.total_cost == 350000.0
        assert stored.realized_income == 1200.0
        assert stored.cash_dividend == 200.0

    @pytest.mark.scenario("SC-086")
    def test_sc086_accumulate_without_existing_row_creates_net_only_row(
        self, record_repo, seeded_holding_id
    ):
        record_repo.accumulate_net_investments(
            records=[_record(seeded_holding_id, "2026-05", 0.0, -100000.0)]
        )
        record_repo.accumulate_net_investments(
            records=[_record(seeded_holding_id, "2026-05", 0.0, -50000.0)]
        )

        stored = record_repo.read_month(year_month="2026-05")[0]
        assert stored.market_value is None
        assert stored.net_investment == -150000.0
        assert stored.total_cost is None
        assert stored.realized_income is None
        assert stored.cash_dividend is None

    @pytest.mark.scenario("SC-086")
    def test_sc086_transfer_then_single_row_input_gives_same_result(
        self, record_repo, seeded_holding_id
    ):
        # 先轉移（無既有列）、再單列錄入補市值：錄入帶入的淨投入為累加後的值
        record_repo.accumulate_net_investments(
            records=[_record(seeded_holding_id, "2026-05", 0.0, -150000.0)]
        )
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 350000.0, -150000.0)
        )

        stored = record_repo.read_month(year_month="2026-05")[0]
        assert stored.market_value == 350000.0
        assert stored.net_investment == -150000.0

    @pytest.mark.scenario("SC-086")
    def test_sc086_accumulate_empty_list_is_noop(self, record_repo, seeded_holding_id):
        record_repo.accumulate_net_investments(records=[])

        assert record_repo.read_month(year_month="2026-05") == []

    @pytest.mark.scenario("SC-086")
    def test_sc086_accumulate_multiple_holdings_in_one_call(
        self, record_repo, seeded_holding_id
    ):
        record_repo.accumulate_net_investments(
            records=[
                _record(seeded_holding_id, "2026-05", 0.0, 30000.0),
                _record(seeded_holding_id, "2026-06", 0.0, 40000.0),
            ]
        )

        assert record_repo.read_month(year_month="2026-05")[0].net_investment == 30000.0
        assert record_repo.read_month(year_month="2026-06")[0].net_investment == 40000.0

    @pytest.mark.scenario("SC-085")
    def test_sc085_accumulate_failure_rolls_back_all_writes(
        self, record_repo, conn, seeded_holding_id
    ):
        record_repo.upsert_record(
            record=_record(seeded_holding_id, "2026-05", 350000.0, 1000.0)
        )
        failing_repo = RecordRepository(conn=_FailAfterNCallsConnection(conn, fail_at=2))

        with pytest.raises(RuntimeError, match="模擬批次寫入中途失敗"):
            failing_repo.accumulate_net_investments(
                records=[
                    _record(seeded_holding_id, "2026-05", 0.0, -100000.0),
                    _record(seeded_holding_id, "2026-06", 0.0, -50000.0),
                ]
            )

        assert record_repo.read_month(year_month="2026-05")[0].net_investment == 1000.0
        assert record_repo.read_month(year_month="2026-06") == []


class TestBuildRecordPrefill:
    """build_record_prefill：一般分類錄入框帶入當月既有值 —— SC-087。"""

    @pytest.mark.scenario("SC-087")
    def test_sc087_existing_record_prefilled_as_stored(self):
        records = [_prev_record(1, "2026-05", 350000.0, -150000.0)]
        prefill = _service(_StubRecordRepo(latest_ym=None)).build_record_prefill(
            records=records, holding_id=1, year_month="2026-05"
        )
        assert prefill.market_value == 350000.0
        assert prefill.net_investment == -150000.0

    @pytest.mark.scenario("SC-087")
    def test_sc087_no_record_for_holding_market_value_blank_net_investment_zero(self):
        # 「活存」有紀錄、「定存」該月無紀錄 → 定存回現行預設
        records = [_prev_record(1, "2026-05", 350000.0, -150000.0)]
        prefill = _service(_StubRecordRepo(latest_ym=None)).build_record_prefill(
            records=records, holding_id=2, year_month="2026-05"
        )
        assert prefill.market_value is None
        assert prefill.net_investment == 0.0

    @pytest.mark.scenario("SC-087")
    def test_sc087_empty_records_market_value_blank_net_investment_zero(self):
        prefill = _service(_StubRecordRepo(latest_ym=None)).build_record_prefill(
            records=[], holding_id=1, year_month="2026-05"
        )
        assert prefill.market_value is None
        assert prefill.net_investment == 0.0

    @pytest.mark.scenario("SC-087")
    def test_sc087_null_market_value_prefilled_as_blank_not_zero(self):
        records = [_prev_record(1, "2026-05", None, 200.0)]
        prefill = _service(_StubRecordRepo(latest_ym=None)).build_record_prefill(
            records=records, holding_id=1, year_month="2026-05"
        )
        assert prefill.market_value is None
        assert prefill.net_investment == 200.0

    @pytest.mark.scenario("SC-087")
    def test_sc087_other_month_record_not_matched(self):
        records = [_prev_record(1, "2026-04", 999.0, 5.0)]
        prefill = _service(_StubRecordRepo(latest_ym=None)).build_record_prefill(
            records=records, holding_id=1, year_month="2026-05"
        )
        assert prefill.market_value is None
        assert prefill.net_investment == 0.0


class TestSummarizeMonth:
    """summarize_month：本月已存紀錄彙總與市值未填提醒 —— SC-089。"""

    @pytest.mark.scenario("SC-089")
    def test_sc089_rows_follow_record_order_with_matched_names(self):
        holdings = [_asset(1, "活存"), _liability(2, "房貸"), _asset(3, "聯發科")]
        records = [
            _prev_record(1, "2026-06", 370000.0),
            _prev_record(2, "2026-06", None),
            MonthlyRecordModel(
                holding_id=3,
                year_month="2026-06",
                market_value=0.0,
                net_investment=-100.0,
                total_cost=0.0,
                realized_income=50000.0,
            ),
        ]
        rows = _service(_StubRecordRepo(latest_ym=None)).summarize_month(
            records=records, holdings=holdings
        )
        assert [row.name for row in rows] == ["活存", "房貸", "聯發科"]
        assert [row.holding_id for row in rows] == [1, 2, 3]
        assert rows[0].market_value == 370000.0
        assert rows[0].total_cost is None
        assert rows[0].realized_income is None
        assert rows[2].net_investment == -100.0
        assert rows[2].total_cost == 0.0
        assert rows[2].realized_income == 50000.0

    @pytest.mark.scenario("SC-089")
    def test_sc089_missing_flag_only_for_blank_market_value_including_liability(self):
        holdings = [_asset(1, "活存"), _liability(2, "房貸"), _asset(3, "聯發科")]
        records = [
            _prev_record(1, "2026-06", 370000.0),
            _prev_record(2, "2026-06", None),
            _prev_record(3, "2026-06", 0.0),
        ]
        rows = _service(_StubRecordRepo(latest_ym=None)).summarize_month(
            records=records, holdings=holdings
        )
        # 市值 0 是已填（出清語意），不提醒；只有空白（含負債）才提醒
        assert [row.market_value_missing for row in rows] == [False, True, False]

    @pytest.mark.scenario("SC-089")
    def test_sc089_no_records_returns_empty_list(self):
        rows = _service(_StubRecordRepo(latest_ym=None)).summarize_month(
            records=[], holdings=[_asset(1, "活存")]
        )
        assert rows == []
