# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import libsql
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository


@pytest.fixture
def conn():
    """每個 test 一個獨立記憶體 DB，建好三表後交給 Repository（不連任何遠端 Turso）。"""
    connection = libsql.connect(":memory:")
    SchemaRepository(conn=connection).ensure_schema()
    yield connection


@pytest.fixture
def holding_repo(conn):
    return HoldingRepository(conn=conn)


@pytest.fixture
def record_repo(conn):
    return RecordRepository(conn=conn)


def _asset(name: str, category: str, imv: float, ic: float) -> HoldingModel:
    """組一個資產項目主檔（holding_id 由 DB 產生，新增時為 None）。"""
    return HoldingModel(
        holding_id=None,
        name=name,
        kind=HOLDING_KIND.ASSET,
        category=category,
        initial_market_value=imv,
        initial_cost=ic,
    )


def _liability(name: str) -> HoldingModel:
    """組一個負債項目主檔（無分類、無初始市值/成本）。"""
    return HoldingModel(
        holding_id=None,
        name=name,
        kind=HOLDING_KIND.LIABILITY,
        category=None,
        initial_market_value=None,
        initial_cost=None,
    )


class TestAddAssetHolding:
    """SC-001：新增資產項目並記錄分類與初始市值/初始成本。"""

    @pytest.mark.scenario("SC-001")
    def test_sc001_add_asset_persists_category_and_initials(self, holding_repo):
        # 新增「台積電」資產，分類台股、初始市值 500000、初始成本 300000
        new_id = holding_repo.add_holding(
            holding=_asset("台積電", ASSET_CATEGORIES.TW_STOCK, 500000.0, 300000.0)
        )
        # 主檔可依穩定身分讀回，分類與初始市值/成本完整保留
        stored = holding_repo.get_holding(holding_id=new_id)
        assert stored is not None
        assert stored.holding_id == new_id
        assert stored.name == "台積電"
        assert stored.kind == HOLDING_KIND.ASSET
        assert stored.category == ASSET_CATEGORIES.TW_STOCK
        assert stored.initial_market_value == 500000.0
        assert stored.initial_cost == 300000.0

    @pytest.mark.scenario("SC-001")
    def test_sc001_add_returns_distinct_stable_ids(self, holding_repo):
        # 連續新增的項目各自取得不同的穩定身分（自動遞增、不重用）
        id1 = holding_repo.add_holding(
            holding=_asset("台積電", ASSET_CATEGORIES.TW_STOCK, 500000.0, 300000.0)
        )
        id2 = holding_repo.add_holding(
            holding=_asset("0050", ASSET_CATEGORIES.TW_STOCK, 200000.0, 200000.0)
        )
        assert id1 != id2

    @pytest.mark.scenario("SC-001")
    def test_sc001_new_buy_initial_market_value_equals_cost(self, holding_repo):
        # 新買進項目：初始市值與初始成本可相等（皆 300000）
        new_id = holding_repo.add_holding(
            holding=_asset("新買 ETF", ASSET_CATEGORIES.TW_STOCK, 300000.0, 300000.0)
        )
        stored = holding_repo.get_holding(holding_id=new_id)
        assert stored.initial_market_value == stored.initial_cost == 300000.0

    @pytest.mark.scenario("SC-001")
    def test_sc001_legacy_holding_initial_market_value_differs_from_cost(self, holding_repo):
        # 舊持倉項目：初始市值（500000）與初始成本（300000）不相等，兩者各自獨立保存
        new_id = holding_repo.add_holding(
            holding=_asset("舊持倉", ASSET_CATEGORIES.TW_STOCK, 500000.0, 300000.0)
        )
        stored = holding_repo.get_holding(holding_id=new_id)
        assert stored.initial_market_value == 500000.0
        assert stored.initial_cost == 300000.0
        assert stored.initial_market_value != stored.initial_cost

    @pytest.mark.scenario("SC-001")
    def test_sc001_added_holding_appears_in_list(self, holding_repo):
        # 新增後出現在主檔清單中
        new_id = holding_repo.add_holding(
            holding=_asset("台積電", ASSET_CATEGORIES.TW_STOCK, 500000.0, 300000.0)
        )
        listed = holding_repo.list_holdings()
        assert [h.holding_id for h in listed] == [new_id]


class TestAddLiabilityHolding:
    """SC-002：新增負債項目不記分類與初始成本。"""

    @pytest.mark.scenario("SC-002")
    def test_sc002_add_liability_has_no_category_or_initials(self, holding_repo):
        # 新增「房貸」負債：性質為負債，不歸屬分類、不記初始市值/成本
        new_id = holding_repo.add_holding(holding=_liability("房貸"))
        stored = holding_repo.get_holding(holding_id=new_id)
        assert stored is not None
        assert stored.name == "房貸"
        assert stored.kind == HOLDING_KIND.LIABILITY
        assert stored.category is None
        assert stored.initial_market_value is None
        assert stored.initial_cost is None

    @pytest.mark.scenario("SC-002")
    def test_sc002_liability_listed_alongside_assets(self, holding_repo):
        # 負債與資產同列於主檔清單，負債仍維持無分類/無初始值
        holding_repo.add_holding(
            holding=_asset("台積電", ASSET_CATEGORIES.TW_STOCK, 500000.0, 300000.0)
        )
        liab_id = holding_repo.add_holding(holding=_liability("房貸"))
        liability = holding_repo.get_holding(holding_id=liab_id)
        assert liability.kind == HOLDING_KIND.LIABILITY
        assert liability.category is None
        assert {h.kind for h in holding_repo.list_holdings()} == {
            HOLDING_KIND.ASSET,
            HOLDING_KIND.LIABILITY,
        }


class TestRenameKeepsStableIdentity:
    """SC-003：改項目名稱不影響歷史報酬連乘（穩定 holding_id）。"""

    @pytest.mark.scenario("SC-003")
    def test_sc003_rename_keeps_same_holding_id(self, holding_repo):
        # 新增「台積電」後改名為「TSMC」：holding_id 不變，名稱更新
        original_id = holding_repo.add_holding(
            holding=_asset("台積電", ASSET_CATEGORIES.TW_STOCK, 500000.0, 300000.0)
        )
        renamed = holding_repo.get_holding(holding_id=original_id)
        renamed.name = "TSMC"
        holding_repo.update_holding(holding=renamed)
        after = holding_repo.get_holding(holding_id=original_id)
        assert after.holding_id == original_id
        assert after.name == "TSMC"

    @pytest.mark.scenario("SC-003")
    def test_sc003_history_records_still_bound_to_same_id_after_rename(
        self, holding_repo, record_repo
    ):
        # 項目已有跨多月紀錄；改名後所有歷史月份仍歸屬同一穩定身分（holding_id）
        original_id = holding_repo.add_holding(
            holding=_asset("台積電", ASSET_CATEGORIES.TW_STOCK, 500000.0, 300000.0)
        )
        for ym, mv in [("2026-01", 510000.0), ("2026-02", 520000.0), ("2026-03", 540000.0)]:
            record_repo.upsert_record(
                record=MonthlyRecordModel(
                    holding_id=original_id, year_month=ym, market_value=mv, net_investment=0.0
                )
            )
        before_history = record_repo.read_range(start_ym="2026-01", end_ym="2026-03")

        renamed = holding_repo.get_holding(holding_id=original_id)
        renamed.name = "TSMC"
        holding_repo.update_holding(holding=renamed)

        after_history = record_repo.read_range(start_ym="2026-01", end_ym="2026-03")
        # 歷史紀錄筆數、所掛 holding_id 與各月市值序列改名前後完全一致（連乘輸入不變）
        assert list(after_history["holding_id"]) == [original_id] * 3
        assert list(after_history["market_value"]) == list(before_history["market_value"])
        assert list(after_history["year_month"]) == ["2026-01", "2026-02", "2026-03"]


class TestRecategorizeIsNotTimeVersioned:
    """SC-004：改項目分類後歷史月份以當前分類回溯重算（分類非時間版本化）。"""

    @pytest.mark.scenario("SC-004")
    def test_sc004_category_change_applies_to_all_history(self, holding_repo, record_repo):
        # 項目原分類「活存」，已有 1~3 月市值紀錄
        original_id = holding_repo.add_holding(
            holding=_asset("活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, 100000.0, 100000.0)
        )
        for ym in ("2026-01", "2026-02", "2026-03"):
            record_repo.upsert_record(
                record=MonthlyRecordModel(
                    holding_id=original_id, year_month=ym, market_value=100000.0
                )
            )
        # 改分類為「台股/台股ETF」
        holding = holding_repo.get_holding(holding_id=original_id)
        holding.category = ASSET_CATEGORIES.TW_STOCK
        holding_repo.update_holding(holding=holding)

        # 主檔只保有「當前分類」，無逐月分類版本；歷史佔比回溯時皆讀到台股分類
        after = holding_repo.get_holding(holding_id=original_id)
        assert after.category == ASSET_CATEGORIES.TW_STOCK
        # 三個月紀錄不帶任何分類欄位（分類只存於主檔，非時間版本化）
        history = record_repo.read_range(start_ym="2026-01", end_ym="2026-03")
        assert "category" not in history.columns

    @pytest.mark.scenario("SC-004")
    def test_sc004_no_per_month_category_snapshot_stored(self, holding_repo, record_repo):
        # 分類改兩次後，主檔僅反映最後一次（不累積任何歷史分類版本）
        original_id = holding_repo.add_holding(
            holding=_asset("活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, 100000.0, 100000.0)
        )
        record_repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=original_id, year_month="2026-01", market_value=100000.0
            )
        )
        holding = holding_repo.get_holding(holding_id=original_id)
        holding.category = ASSET_CATEGORIES.TW_STOCK
        holding_repo.update_holding(holding=holding)
        holding.category = ASSET_CATEGORIES.US_STOCK
        holding_repo.update_holding(holding=holding)
        latest = holding_repo.get_holding(holding_id=original_id)
        assert latest.category == ASSET_CATEGORIES.US_STOCK
