"""bootstrap.py 的可測組裝邏輯測試。

bootstrap 的 st.cache_resource 包裝與 st.secrets 讀取屬無法純測的 Streamlit runtime 副作用，
但其中幾段邏輯是純函式、與 runtime 無關，故抽出獨立測試：

1. parse_allowed_emails：把 st.secrets 讀回的允許清單原始值（可能是清單、逗號分隔字串或
   單一字串）正規化成 set，供守門判定（t10 的 evaluate_access）使用。允許 email 屬個資，
   測試一律用虛構值，不出現任何真實 email（遵守敏感資料護欄）。
2. build_container：以 keyword args 把連線注入各 Repository、再把 Repository 注入各 Service，
   組出單一容器。可注入假連線斷言「依賴有被正確接上」，不需 Streamlit runtime。
3. _with_reconnect_on_stale_stream：Turso 遠端連線的 Hrana stream 閒置隔夜會被伺服器端
   關閉，快取住的連線與容器不會自動感知，下次操作即拋「stream not found」類例外整頁崩潰
   （t16 驗收回饋）。此函式把「取容器→驗證存活→失效則清快取重連重試一次」收斂成可注入
   假容器/假快取清除動作的純函式，故以假物件模擬連線失效與重連成功，不需真連 Turso。

另補一段版控範本 secrets.toml.example 的結構回歸測試：TOML 語法中，區塊標頭
（`[section]`）之後、下一個標頭之前的所有 key 都歸屬該區塊，`allowed_emails` 若被放在
`[turso]` 與 `[auth]` 之間會被誤歸入 `turso.allowed_emails`，導致 allowed_emails() 讀
不到頂層值而 fail-closed 擋下所有人（含合法使用者）。此測試鎖定範本解析後的結構。
"""

# ==== 原生（標準庫） ====
import ast
import logging
import sys
import tomllib
from pathlib import Path
from unittest.mock import Mock

# ==== 第三方套件 ====
import libsql
import pytest
from streamlit.errors import StreamlitSecretNotFoundError

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.constants import (
    APP_LOGGING,
    ASSET_CATEGORIES,
    BALANCE_INPUT,
    COST_BASIS_INPUT,
    HOLDING_KIND,
    HOLDING_PURPOSE,
    HOLDINGS_TABLE,
    INPUT_MODE,
    MONTHLY_RECORDS_TABLE,
    PREMIUM_INPUT,
    READ_CACHE,
)
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.repositories.connection_layers import CachingConnection, CountingConnection
from asset_lab.repositories.health_repository import ConnectionHealthRepository
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.protocol_threshold_repository import ProtocolThresholdRepository
from asset_lab.repositories.query_metrics import QueryMetrics
from asset_lab.repositories.read_cache import ReadCache
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.repositories.transaction_repository import TransactionRepository
from asset_lab.services.affordability_service import AffordabilityService
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.balance_input_service import BalanceInputService
from asset_lab.services.cost_basis_service import CostBasisService
from asset_lab.services.data_io_service import DataIoService
from asset_lab.services.monthly_input_service import MonthlyInputService
from asset_lab.services.period_service import PeriodService
from asset_lab.services.protocol_service import ProtocolService
from asset_lab.services.return_service import ReturnService

APP_DIR = Path(__file__).resolve().parent.parent


class _FakeConnection:
    """假連線：只佔位以驗證 Repository 是否接上同一連線，不執行任何 I/O。"""


@pytest.mark.scenario("SC-033")
def test_parse_allowed_emails_from_list_normalizes_and_dedupes() -> None:
    """清單型允許值去前後空白、轉小寫並去重，產出供守門比對的 set。"""
    raw = ["Owner@Example.com", " owner@example.com ", "alt@example.com"]

    result = bootstrap.parse_allowed_emails(raw)

    assert result == {"owner@example.com", "alt@example.com"}


@pytest.mark.scenario("SC-033")
def test_parse_allowed_emails_from_comma_separated_string() -> None:
    """逗號分隔字串拆成多個 email 並各自正規化（secrets 常以單行字串設定）。"""
    raw = "Owner@Example.com, alt@example.com"

    result = bootstrap.parse_allowed_emails(raw)

    assert result == {"owner@example.com", "alt@example.com"}


@pytest.mark.scenario("SC-033")
def test_parse_allowed_emails_from_single_string() -> None:
    """單一 email 字串（無逗號）正規化成單元素 set。"""
    result = bootstrap.parse_allowed_emails("Owner@Example.com")

    assert result == {"owner@example.com"}


@pytest.mark.scenario("SC-034")
def test_parse_allowed_emails_empty_yields_empty_set() -> None:
    """允許清單未設定（None / 空字串 / 空清單）時回空 set，守門將不放行任何人。"""
    assert bootstrap.parse_allowed_emails(None) == set()
    assert bootstrap.parse_allowed_emails("") == set()
    assert bootstrap.parse_allowed_emails("   ") == set()
    assert bootstrap.parse_allowed_emails([]) == set()


@pytest.mark.scenario("SC-034")
def test_parse_allowed_emails_skips_blank_entries() -> None:
    """逗號分隔中夾帶空白片段（如尾逗號）不應產生空字串成員。"""
    result = bootstrap.parse_allowed_emails("owner@example.com, , ")

    assert result == {"owner@example.com"}


@pytest.mark.scenario("SC-034")
def test_allowed_emails_returns_empty_when_no_secrets_file(monkeypatch) -> None:
    """完全沒有 secrets 檔時 allowed_emails 回空 set（fail-closed），不讓守門崩潰。"""

    class _NoSecrets:
        def get(self, key):
            raise StreamlitSecretNotFoundError("No secrets found")

    monkeypatch.setattr(bootstrap.st, "secrets", _NoSecrets())

    assert bootstrap.allowed_emails() == set()


@pytest.mark.scenario("SC-033")
def test_allowed_emails_reads_and_normalizes_from_secrets(monkeypatch) -> None:
    """有設定時 allowed_emails 從 secrets 取值並正規化（虛構值，不寫死真實 email）。"""

    class _Secrets:
        def get(self, key):
            return ["Owner@Example.com"] if key == "allowed_emails" else None

    monkeypatch.setattr(bootstrap.st, "secrets", _Secrets())

    assert bootstrap.allowed_emails() == {"owner@example.com"}


def test_build_container_wires_repositories_to_connection() -> None:
    """容器以注入的同一連線建立各 Repository，並由 DB schema 建表入口備妥。"""
    conn = _FakeConnection()

    container = bootstrap.build_container(
        conn=conn,
        read_cache=ReadCache(ttl_seconds=300),
        query_metrics=QueryMetrics(),
    )

    assert isinstance(container.holding_repo, HoldingRepository)
    assert isinstance(container.record_repo, RecordRepository)
    assert isinstance(container.target_repo, TargetRepository)
    assert isinstance(container.schema_repo, SchemaRepository)
    assert isinstance(container.protocol_threshold_repo, ProtocolThresholdRepository)
    assert isinstance(container.transaction_repo, TransactionRepository)
    # 連線分層：Repository 接快取層，快取層包計數層，計數層包住注入的連線
    cached = container.holding_repo._conn
    assert isinstance(cached, CachingConnection)
    counted = cached._inner
    assert isinstance(counted, CountingConnection)
    assert counted._inner is conn
    assert container.record_repo._conn is cached
    assert container.target_repo._conn is cached
    assert container.protocol_threshold_repo._conn is cached
    assert container.transaction_repo._conn is cached
    # 建表 Repository 不經快取，直接接計數層
    assert container.schema_repo._conn is not cached
    assert isinstance(container.schema_repo._conn, CountingConnection)
    assert container.schema_repo._conn._inner is conn


def test_build_container_wires_services() -> None:
    """容器組出各 Service；月度錄入服務接上主檔與紀錄 Repository（其餘為純運算無依賴）。"""
    conn = _FakeConnection()

    container = bootstrap.build_container(
        conn=conn,
        read_cache=ReadCache(ttl_seconds=300),
        query_metrics=QueryMetrics(),
    )

    assert isinstance(container.return_service, ReturnService)
    assert isinstance(container.allocation_service, AllocationService)
    assert isinstance(container.period_service, PeriodService)
    assert isinstance(container.data_io_service, DataIoService)
    assert isinstance(container.monthly_input_service, MonthlyInputService)
    assert isinstance(container.cost_basis_service, CostBasisService)
    assert isinstance(container.protocol_service, ProtocolService)
    assert isinstance(container.affordability_service, AffordabilityService)
    # 月度錄入服務的 I/O 委派接上容器內的 Repository 實例
    assert container.monthly_input_service._record_repo is container.record_repo
    assert container.monthly_input_service._holding_repo is container.holding_repo
    # 錄入方式解析的對照表、負債性質與負債錄入方式皆注入自常數
    assert (
        container.monthly_input_service._input_mode_by_category == INPUT_MODE.BY_ASSET_CATEGORY
    )
    assert container.monthly_input_service._liability_kind == HOLDING_KIND.LIABILITY
    assert container.monthly_input_service._liability_input_mode == INPUT_MODE.AMOUNT_DUE
    # 總成本推算服務的分類集合注入自常數，不寫死在組裝邏輯裡
    assert container.cost_basis_service.cost_basis_categories == COST_BASIS_INPUT.CATEGORIES
    # 保險累計保費推算的分類集合同樣注入自常數
    assert container.cost_basis_service.premium_categories == PREMIUM_INPUT.CATEGORIES
    # 活存/定存餘額推算服務的分類集合同樣注入自常數
    assert isinstance(container.balance_input_service, BalanceInputService)
    assert container.balance_input_service.balance_categories == BALANCE_INPUT.CATEGORIES


# === holdings 用途欄位加欄遷移：舊庫升級 / 新庫直建 / 重複啟動三路徑 ===

# 本 Change 之前（無 purpose 欄）的 holdings 表結構，直接以原始 SQL 建出，模擬既有部署
# 資料庫；不可呼叫現行 SchemaRepository._CREATE_HOLDINGS（其已含 purpose 欄，無法重現
# 舊庫缺欄的情境）。
_LEGACY_CREATE_HOLDINGS = f"""
CREATE TABLE {HOLDINGS_TABLE.TABLE_NAME} (
    {HOLDINGS_TABLE.HOLDING_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
    {HOLDINGS_TABLE.NAME} TEXT NOT NULL,
    {HOLDINGS_TABLE.KIND} TEXT NOT NULL,
    {HOLDINGS_TABLE.CATEGORY} TEXT,
    {HOLDINGS_TABLE.INITIAL_MARKET_VALUE} REAL,
    {HOLDINGS_TABLE.INITIAL_COST} REAL,
    {HOLDINGS_TABLE.CREATED_AT} TEXT
)
"""


def _seed_legacy_holdings_db() -> "libsql.Connection":
    """建一個模擬「本 Change 之前」的既有資料庫：holdings 表無 purpose 欄，已有 3 筆項目。"""
    connection = libsql.connect(":memory:")
    cursor = connection.cursor()
    cursor.execute(_LEGACY_CREATE_HOLDINGS)
    for name, category, market_value in (
        ("範例定存", ASSET_CATEGORIES.TIME_DEPOSIT, 10000.0),
        ("範例活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, 20000.0),
        ("範例房貸", None, None),
    ):
        cursor.execute(
            f"INSERT INTO {HOLDINGS_TABLE.TABLE_NAME} "
            f"({HOLDINGS_TABLE.NAME}, {HOLDINGS_TABLE.KIND}, {HOLDINGS_TABLE.CATEGORY}, "
            f"{HOLDINGS_TABLE.INITIAL_MARKET_VALUE}, {HOLDINGS_TABLE.INITIAL_COST}) "
            f"VALUES (?, ?, ?, ?, ?)",
            (
                name,
                HOLDING_KIND.LIABILITY if category is None else HOLDING_KIND.ASSET,
                category,
                market_value,
                market_value,
            ),
        )
    connection.commit()
    return connection


class TestHoldingsPurposeMigrationLegacyUpgrade:
    """既有（本 Change 之前）資料庫首次啟動升級：既有項目自動補一般用途，資料無遺失。"""

    @pytest.mark.scenario("SC-059")
    def test_sc059_legacy_db_upgrade_backfills_general_purpose(self) -> None:
        connection = _seed_legacy_holdings_db()

        SchemaRepository(conn=connection).ensure_schema()

        holdings = HoldingRepository(conn=connection).list_holdings()
        assert len(holdings) == 3
        assert {h.purpose for h in holdings} == {HOLDING_PURPOSE.GENERAL}

    @pytest.mark.scenario("SC-059")
    def test_sc059_legacy_db_upgrade_preserves_existing_fields(self) -> None:
        connection = _seed_legacy_holdings_db()

        SchemaRepository(conn=connection).ensure_schema()

        holdings = {h.name: h for h in HoldingRepository(conn=connection).list_holdings()}
        deposit = holdings["範例定存"]
        assert deposit.category == ASSET_CATEGORIES.TIME_DEPOSIT
        assert deposit.initial_market_value == 10000.0
        assert deposit.initial_cost == 10000.0
        liability = holdings["範例房貸"]
        assert liability.kind == HOLDING_KIND.LIABILITY
        assert liability.category is None
        assert liability.initial_market_value is None

    @pytest.mark.scenario("SC-059")
    def test_sc059_upgraded_legacy_holding_can_be_edited_to_house_purpose(self) -> None:
        # 升級後舊庫的既有項目可正常編輯為「購屋」用途
        connection = _seed_legacy_holdings_db()
        SchemaRepository(conn=connection).ensure_schema()
        repo = HoldingRepository(conn=connection)
        deposit = next(h for h in repo.list_holdings() if h.name == "範例定存")

        deposit.purpose = HOLDING_PURPOSE.HOUSE
        repo.update_holding(holding=deposit)

        reloaded = repo.get_holding(holding_id=deposit.holding_id)
        assert reloaded.purpose == HOLDING_PURPOSE.HOUSE

    @pytest.mark.scenario("SC-059")
    def test_sc059_repeated_ensure_schema_on_upgraded_db_is_idempotent(self) -> None:
        # 重複啟動安全：升級後再跑 2、3 次 ensure_schema 不報錯、既有資料不重複變更
        connection = _seed_legacy_holdings_db()
        schema_repo = SchemaRepository(conn=connection)

        schema_repo.ensure_schema()
        schema_repo.ensure_schema()
        schema_repo.ensure_schema()

        holdings = HoldingRepository(conn=connection).list_holdings()
        assert len(holdings) == 3
        assert {h.purpose for h in holdings} == {HOLDING_PURPOSE.GENERAL}


class TestHoldingsPurposeMigrationFreshDb:
    """全新資料庫首次啟動：直接支援用途標記，行為與升級後的舊庫一致。"""

    @pytest.mark.scenario("SC-059")
    def test_sc059_fresh_db_supports_purpose_immediately(self) -> None:
        connection = libsql.connect(":memory:")

        SchemaRepository(conn=connection).ensure_schema()

        repo = HoldingRepository(conn=connection)
        new_id = repo.add_holding(
            holding=HoldingModel(
                name="新建定存",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TIME_DEPOSIT,
                initial_market_value=5000.0,
                initial_cost=5000.0,
                purpose=HOLDING_PURPOSE.HOUSE,
            )
        )

        stored = repo.get_holding(holding_id=new_id)
        assert stored.purpose == HOLDING_PURPOSE.HOUSE

    @pytest.mark.scenario("SC-059")
    def test_sc059_fresh_db_new_holding_without_explicit_purpose_defaults_to_general(
        self,
    ) -> None:
        connection = libsql.connect(":memory:")
        SchemaRepository(conn=connection).ensure_schema()
        repo = HoldingRepository(conn=connection)

        new_id = repo.add_holding(
            holding=HoldingModel(
                name="新建活存",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.DEMAND_DEPOSIT,
                initial_market_value=1000.0,
                initial_cost=1000.0,
            )
        )

        assert repo.get_holding(holding_id=new_id).purpose == HOLDING_PURPOSE.GENERAL

    @pytest.mark.scenario("SC-059")
    def test_sc059_repeated_ensure_schema_on_fresh_db_is_idempotent(self) -> None:
        # 重複啟動安全：全新庫也可重跑 ensure_schema 多次，不報錯、既有資料不受影響
        connection = libsql.connect(":memory:")
        schema_repo = SchemaRepository(conn=connection)
        schema_repo.ensure_schema()
        repo = HoldingRepository(conn=connection)
        new_id = repo.add_holding(
            holding=HoldingModel(
                name="新建定存",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TIME_DEPOSIT,
                initial_market_value=2000.0,
                initial_cost=2000.0,
            )
        )

        schema_repo.ensure_schema()
        schema_repo.ensure_schema()

        stored = repo.get_holding(holding_id=new_id)
        assert stored is not None
        assert stored.purpose == HOLDING_PURPOSE.GENERAL


# === monthly_records 總成本/已實現收益欄位加欄遷移：舊庫升級 / 新庫直建 / 重複啟動三路徑 ===

# 本 Change 之前（無 total_cost/realized_income 欄）的 monthly_records 表結構，直接以原始
# SQL 建出，模擬既有部署資料庫；不可呼叫現行 SchemaRepository._CREATE_MONTHLY_RECORDS
# （其已含兩個新欄，無法重現舊庫缺欄的情境）。
_LEGACY_CREATE_MONTHLY_RECORDS = f"""
CREATE TABLE {MONTHLY_RECORDS_TABLE.TABLE_NAME} (
    {MONTHLY_RECORDS_TABLE.HOLDING_ID} INTEGER NOT NULL,
    {MONTHLY_RECORDS_TABLE.YEAR_MONTH} TEXT NOT NULL,
    {MONTHLY_RECORDS_TABLE.MARKET_VALUE} REAL,
    {MONTHLY_RECORDS_TABLE.NET_INVESTMENT} REAL NOT NULL DEFAULT 0,
    PRIMARY KEY ({MONTHLY_RECORDS_TABLE.HOLDING_ID}, {MONTHLY_RECORDS_TABLE.YEAR_MONTH})
)
"""


def _seed_legacy_monthly_records_db() -> "libsql.Connection":
    """建一個模擬「本功能上線前」的既有資料庫：monthly_records 表無新欄，已有 2 筆紀錄。"""
    connection = libsql.connect(":memory:")
    cursor = connection.cursor()
    cursor.execute(_LEGACY_CREATE_MONTHLY_RECORDS)
    for holding_id, year_month, market_value, net_investment in (
        (1, "2026-01", 500000.0, 0.0),
        (2, "2026-01", 20000.0, 30000.0),
    ):
        cursor.execute(
            f"INSERT INTO {MONTHLY_RECORDS_TABLE.TABLE_NAME} "
            f"({MONTHLY_RECORDS_TABLE.HOLDING_ID}, {MONTHLY_RECORDS_TABLE.YEAR_MONTH}, "
            f"{MONTHLY_RECORDS_TABLE.MARKET_VALUE}, {MONTHLY_RECORDS_TABLE.NET_INVESTMENT}) "
            f"VALUES (?, ?, ?, ?)",
            (holding_id, year_month, market_value, net_investment),
        )
    connection.commit()
    return connection


class TestMonthlyRecordsCostColumnsMigrationLegacyUpgrade:
    """既有（本功能上線前）資料庫首次啟動升級：既有紀錄補上 total_cost/realized_income 為
    NULL（＝舊制列），資料無遺失。"""

    @pytest.mark.scenario("SC-006")
    def test_sc006_legacy_db_upgrade_adds_nullable_cost_columns(self) -> None:
        connection = _seed_legacy_monthly_records_db()

        SchemaRepository(conn=connection).ensure_schema()

        records = RecordRepository(conn=connection).read_month(year_month="2026-01")
        assert len(records) == 2
        assert {r.total_cost for r in records} == {None}
        assert {r.realized_income for r in records} == {None}

    @pytest.mark.scenario("SC-006")
    def test_sc006_legacy_db_upgrade_preserves_existing_values(self) -> None:
        connection = _seed_legacy_monthly_records_db()

        SchemaRepository(conn=connection).ensure_schema()

        records = {
            r.holding_id: r
            for r in RecordRepository(conn=connection).read_month(year_month="2026-01")
        }
        assert records[1].market_value == 500000.0
        assert records[2].net_investment == 30000.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_upgraded_legacy_record_can_be_edited_with_cost_columns(self) -> None:
        # 升級後舊庫的既有列可正常編輯，補上總成本／已實現收益成為新制列
        connection = _seed_legacy_monthly_records_db()
        SchemaRepository(conn=connection).ensure_schema()
        repo = RecordRepository(conn=connection)

        repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=1,
                year_month="2026-01",
                market_value=510000.0,
                net_investment=0.0,
                total_cost=350000.0,
                realized_income=0.0,
            )
        )

        edited = next(
            r for r in repo.read_month(year_month="2026-01") if r.holding_id == 1
        )
        assert edited.total_cost == 350000.0
        assert edited.realized_income == 0.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_repeated_ensure_schema_on_upgraded_monthly_records_db_is_idempotent(
        self,
    ) -> None:
        # 重複啟動安全：升級後再跑 2、3 次 ensure_schema 不報錯、既有資料不重複變更
        connection = _seed_legacy_monthly_records_db()
        schema_repo = SchemaRepository(conn=connection)

        schema_repo.ensure_schema()
        schema_repo.ensure_schema()
        schema_repo.ensure_schema()

        records = RecordRepository(conn=connection).read_month(year_month="2026-01")
        assert len(records) == 2
        assert {r.total_cost for r in records} == {None}


class TestMonthlyRecordsCostColumnsMigrationFreshDb:
    """全新資料庫首次啟動：直接支援 total_cost/realized_income，行為與升級後的舊庫一致。"""

    @pytest.mark.scenario("SC-006")
    def test_sc006_fresh_db_supports_cost_columns_immediately(self) -> None:
        connection = libsql.connect(":memory:")
        SchemaRepository(conn=connection).ensure_schema()
        repo = RecordRepository(conn=connection)

        repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=1,
                year_month="2026-05",
                market_value=400000.0,
                net_investment=50000.0,
                total_cost=350000.0,
                realized_income=0.0,
            )
        )

        stored = repo.read_month(year_month="2026-05")[0]
        assert stored.total_cost == 350000.0
        assert stored.realized_income == 0.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_fresh_db_new_record_without_cost_columns_defaults_to_null(self) -> None:
        connection = libsql.connect(":memory:")
        SchemaRepository(conn=connection).ensure_schema()
        repo = RecordRepository(conn=connection)

        repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=1,
                year_month="2026-05",
                market_value=400000.0,
                net_investment=50000.0,
            )
        )

        stored = repo.read_month(year_month="2026-05")[0]
        assert stored.total_cost is None
        assert stored.realized_income is None

    @pytest.mark.scenario("SC-006")
    def test_sc006_repeated_ensure_schema_on_fresh_monthly_records_db_is_idempotent(
        self,
    ) -> None:
        # 重複啟動安全：全新庫也可重跑 ensure_schema 多次，不報錯、既有資料不受影響
        connection = libsql.connect(":memory:")
        schema_repo = SchemaRepository(conn=connection)
        schema_repo.ensure_schema()
        repo = RecordRepository(conn=connection)
        repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=1,
                year_month="2026-05",
                market_value=400000.0,
                net_investment=50000.0,
                total_cost=350000.0,
                realized_income=0.0,
            )
        )

        schema_repo.ensure_schema()
        schema_repo.ensure_schema()

        stored = repo.read_month(year_month="2026-05")[0]
        assert stored is not None
        assert stored.total_cost == 350000.0


# === monthly_records 現金股利欄位加欄遷移：6 欄舊庫升級 / 重複啟動 ===

# 前一 Change（已有 total_cost/realized_income，尚無 cash_dividend）的 monthly_records 結構，
# 直接以原始 SQL 建出，模擬既有部署資料庫。
_PREV_CREATE_MONTHLY_RECORDS = f"""
CREATE TABLE {MONTHLY_RECORDS_TABLE.TABLE_NAME} (
    {MONTHLY_RECORDS_TABLE.HOLDING_ID} INTEGER NOT NULL,
    {MONTHLY_RECORDS_TABLE.YEAR_MONTH} TEXT NOT NULL,
    {MONTHLY_RECORDS_TABLE.MARKET_VALUE} REAL,
    {MONTHLY_RECORDS_TABLE.NET_INVESTMENT} REAL NOT NULL DEFAULT 0,
    {MONTHLY_RECORDS_TABLE.TOTAL_COST} REAL,
    {MONTHLY_RECORDS_TABLE.REALIZED_INCOME} REAL,
    PRIMARY KEY ({MONTHLY_RECORDS_TABLE.HOLDING_ID}, {MONTHLY_RECORDS_TABLE.YEAR_MONTH})
)
"""


def _seed_prev_monthly_records_db() -> "libsql.Connection":
    """建一個 6 欄（無 cash_dividend）的既有資料庫，含一筆新制股票列。

    Returns:
        已寫入一筆紀錄的記憶體資料庫連線。
    """
    connection = libsql.connect(":memory:")
    cursor = connection.cursor()
    cursor.execute(_PREV_CREATE_MONTHLY_RECORDS)
    cursor.execute(
        f"INSERT INTO {MONTHLY_RECORDS_TABLE.TABLE_NAME} VALUES (?, ?, ?, ?, ?, ?)",
        (1, "2026-01", 500000.0, 20000.0, 400000.0, 1500.0),
    )
    connection.commit()
    return connection


class TestMonthlyRecordsCashDividendMigration:
    """前一 Change 的 6 欄庫升級後多出可為 NULL 的 cash_dividend，既有值不變。"""

    @pytest.mark.scenario("SC-006")
    def test_sc006_prev_schema_upgrade_adds_nullable_cash_dividend(self) -> None:
        connection = _seed_prev_monthly_records_db()

        SchemaRepository(conn=connection).ensure_schema()

        record = RecordRepository(conn=connection).read_month(year_month="2026-01")[0]
        assert record.cash_dividend is None
        assert record.market_value == 500000.0
        assert record.net_investment == 20000.0
        assert record.total_cost == 400000.0
        assert record.realized_income == 1500.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_prev_schema_repeated_ensure_schema_is_idempotent(self) -> None:
        connection = _seed_prev_monthly_records_db()
        schema_repo = SchemaRepository(conn=connection)

        schema_repo.ensure_schema()
        schema_repo.ensure_schema()

        records = RecordRepository(conn=connection).read_month(year_month="2026-01")
        assert len(records) == 1
        assert records[0].realized_income == 1500.0

    @pytest.mark.scenario("SC-006")
    def test_sc006_fresh_db_round_trips_cash_dividend(self) -> None:
        connection = libsql.connect(":memory:")
        SchemaRepository(conn=connection).ensure_schema()
        repo = RecordRepository(conn=connection)

        repo.upsert_record(
            record=MonthlyRecordModel(
                holding_id=1,
                year_month="2026-05",
                market_value=400000.0,
                total_cost=350000.0,
                realized_income=1200.0,
                cash_dividend=200.0,
            )
        )

        assert repo.read_month(year_month="2026-05")[0].cash_dividend == 200.0


class _FakeHealthRepo:
    """假 health repo：ping 依建構時指定成功或拋指定例外，模擬連線存活探測。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.call_count = 0

    def ping(self) -> None:
        self.call_count += 1
        if self._error is not None:
            raise self._error


class _FakeResilientContainer:
    """假容器：_with_reconnect_on_stale_stream 只用得到 health_repo 這個欄位。"""

    def __init__(self, health_repo: _FakeHealthRepo) -> None:
        self.health_repo = health_repo


def _make_get_container(*containers: _FakeResilientContainer):
    """依序回傳指定的假容器，並記錄實際被呼叫次數，供斷言重試次數上限。"""
    queue = list(containers)

    def _get_container() -> _FakeResilientContainer:
        _get_container.call_count += 1
        return queue.pop(0)

    _get_container.call_count = 0
    return _get_container


def _reconnect_kwargs(get_container, **overrides):
    """組出 _with_reconnect_on_stale_stream 的全部替身參數，個別測試再覆寫要觀察的那幾個。"""
    kwargs = {
        "get_container": get_container,
        "ensure_schema_once": Mock(),
        "clear_connection_cache": Mock(),
        "clear_container_cache": Mock(),
        "on_reconnect": Mock(),
    }
    kwargs.update(overrides)
    return kwargs


_STALE_ERROR = ValueError(
    'Hrana: `api error: `status=404 Not Found, body={"error":"stream not found: abc123"}``'
)


@pytest.mark.scenario("SC-042")
@pytest.mark.scenario("SC-108")
def test_with_reconnect_returns_container_when_connection_alive() -> None:
    """連線存活（ping 成功）時直接回傳容器，只探測一次，不清任何快取、不重取。"""
    container = _FakeResilientContainer(_FakeHealthRepo())
    get_container = _make_get_container(container)
    kwargs = _reconnect_kwargs(get_container)

    result = bootstrap._with_reconnect_on_stale_stream(**kwargs)

    assert result is container
    assert get_container.call_count == 1
    assert container.health_repo.call_count == 1
    kwargs["ensure_schema_once"].assert_called_once_with()
    kwargs["clear_connection_cache"].assert_not_called()
    kwargs["clear_container_cache"].assert_not_called()
    kwargs["on_reconnect"].assert_not_called()


@pytest.mark.scenario("SC-042")
@pytest.mark.scenario("SC-109")
def test_with_reconnect_recovers_from_stale_stream_error() -> None:
    """首次探測拋 stream-not-found 類失效時，清兩層快取重連後重試一次即成功。"""
    dead_container = _FakeResilientContainer(_FakeHealthRepo(error=_STALE_ERROR))
    revived_container = _FakeResilientContainer(_FakeHealthRepo())
    get_container = _make_get_container(dead_container, revived_container)
    kwargs = _reconnect_kwargs(get_container)

    result = bootstrap._with_reconnect_on_stale_stream(**kwargs)

    assert result is revived_container
    assert get_container.call_count == 2
    assert dead_container.health_repo.call_count == 1
    assert revived_container.health_repo.call_count == 1
    kwargs["clear_connection_cache"].assert_called_once()
    kwargs["clear_container_cache"].assert_called_once()
    kwargs["on_reconnect"].assert_called_once_with()


@pytest.mark.scenario("SC-042")
@pytest.mark.scenario("SC-110")
def test_with_reconnect_reraises_non_stale_business_error() -> None:
    """非連線失效的一般例外（如唯一性約束違反）原樣往上拋，不重連、不誤判。"""
    business_error = ValueError("UNIQUE constraint failed: holdings.name")
    container = _FakeResilientContainer(_FakeHealthRepo(error=business_error))
    get_container = _make_get_container(container)
    kwargs = _reconnect_kwargs(get_container)

    with pytest.raises(ValueError, match="UNIQUE constraint failed"):
        bootstrap._with_reconnect_on_stale_stream(**kwargs)

    assert get_container.call_count == 1
    kwargs["clear_connection_cache"].assert_not_called()
    kwargs["clear_container_cache"].assert_not_called()
    kwargs["on_reconnect"].assert_not_called()


@pytest.mark.scenario("SC-042")
@pytest.mark.scenario("SC-110")
def test_with_reconnect_gives_up_after_second_consecutive_failure() -> None:
    """重連重試一次後仍失效，例外原樣浮出，不無限重連（不第三次嘗試）。"""
    first_container = _FakeResilientContainer(_FakeHealthRepo(error=_STALE_ERROR))
    second_container = _FakeResilientContainer(_FakeHealthRepo(error=_STALE_ERROR))
    get_container = _make_get_container(first_container, second_container)
    kwargs = _reconnect_kwargs(get_container)

    with pytest.raises(ValueError, match="stream not found"):
        bootstrap._with_reconnect_on_stale_stream(**kwargs)

    assert get_container.call_count == 2
    assert first_container.health_repo.call_count == 1
    assert second_container.health_repo.call_count == 1
    kwargs["clear_connection_cache"].assert_called_once()
    kwargs["clear_container_cache"].assert_called_once()


@pytest.mark.scenario("SC-110")
def test_with_reconnect_non_stale_error_from_ensure_schema_once_is_not_retried() -> None:
    """建表階段遇到其他錯誤也不重連，直接往上拋。"""
    container = _FakeResilientContainer(_FakeHealthRepo())
    get_container = _make_get_container(container)
    kwargs = _reconnect_kwargs(
        get_container, ensure_schema_once=Mock(side_effect=ValueError("syntax error"))
    )

    with pytest.raises(ValueError, match="syntax error"):
        bootstrap._with_reconnect_on_stale_stream(**kwargs)

    assert get_container.call_count == 1
    kwargs["clear_connection_cache"].assert_not_called()


@pytest.mark.scenario("SC-109")
def test_with_reconnect_does_not_clear_schema_once_cache() -> None:
    """重連只清連線與容器兩層；建表一次的快取不在清除範圍（重連不重新建表）。"""
    dead_container = _FakeResilientContainer(_FakeHealthRepo(error=_STALE_ERROR))
    revived_container = _FakeResilientContainer(_FakeHealthRepo())
    get_container = _make_get_container(dead_container, revived_container)
    kwargs = _reconnect_kwargs(get_container)

    bootstrap._with_reconnect_on_stale_stream(**kwargs)

    # 建表入口是 cache_resource：重連後再叫一次只是命中快取，這裡的契約是不傳入任何清除它的 callable
    assert set(kwargs) == {
        "get_container",
        "ensure_schema_once",
        "clear_connection_cache",
        "clear_container_cache",
        "on_reconnect",
    }


class _RecordingConnection:
    """包住真實 :memory: libsql 連線並記錄所有執行過的 SQL，用於斷言「重連不重新建表」。"""

    def __init__(self, *, stale_on_select_1: bool = False) -> None:
        self._inner = libsql.connect(":memory:")
        self._stale_on_select_1 = stale_on_select_1
        self.statements: list[str] = []

    def cursor(self) -> "_RecordingCursor":
        return _RecordingCursor(owner=self, inner=self._inner.cursor())

    def commit(self) -> None:
        self._inner.commit()

    def rollback(self) -> None:
        self._inner.rollback()


class _RecordingCursor:
    def __init__(self, *, owner: _RecordingConnection, inner) -> None:
        self._owner = owner
        self._inner = inner

    def execute(self, sql: str, parameters=()):
        self._owner.statements.append(sql)
        if self._owner._stale_on_select_1 and sql.strip().upper() == "SELECT 1":
            raise _STALE_ERROR
        self._inner.execute(sql, parameters)
        return self

    def fetchall(self):
        return self._inner.fetchall()

    def fetchone(self):
        return self._inner.fetchone()

    @property
    def lastrowid(self):
        return self._inner.lastrowid


@pytest.fixture
def clean_bootstrap_caches():
    """每個測試前後清掉 bootstrap 的 cache_resource，避免跨測試共用連線與容器。"""
    caches = (
        bootstrap.get_container,
        bootstrap.ensure_schema_once,
        bootstrap.get_read_cache,
        bootstrap.get_query_metrics,
    )
    for cache in caches:
        cache.clear()
    yield
    for cache in caches:
        cache.clear()


class _FakeConnectionFactory:
    """取代 bootstrap.get_connection：依序回傳預先建好的連線，並提供 clear 以模擬重連。"""

    def __init__(self, *connections: _RecordingConnection) -> None:
        self._connections = list(connections)
        self._index = 0
        self.clear_count = 0

    def __call__(self) -> _RecordingConnection:
        return self._connections[self._index]

    def clear(self) -> None:
        self.clear_count += 1
        self._index += 1


def _create_table_statements(conn: _RecordingConnection) -> list[str]:
    return [s for s in conn.statements if "CREATE TABLE" in s.upper()]


@pytest.mark.scenario("SC-108")
def test_sc108_second_resilient_container_call_probes_once_and_does_not_rebuild_schema(
    monkeypatch, clean_bootstrap_caches
) -> None:
    """程序內第二次取容器：不再建表、不再檢查資料表設定，只多一次 SELECT 1。"""
    conn = _RecordingConnection()
    monkeypatch.setattr(bootstrap, "get_connection", _FakeConnectionFactory(conn))
    first = bootstrap.get_resilient_container()
    after_first = len(conn.statements)
    assert _create_table_statements(conn)  # 第一輪確實建了表

    second = bootstrap.get_resilient_container()

    assert second is first
    assert conn.statements[after_first:] == ["SELECT 1"]


@pytest.mark.scenario("SC-108")
def test_sc108_get_container_no_longer_runs_ensure_schema(
    monkeypatch, clean_bootstrap_caches
) -> None:
    conn = _RecordingConnection()
    monkeypatch.setattr(bootstrap, "get_connection", _FakeConnectionFactory(conn))

    bootstrap.get_container()

    assert conn.statements == []


@pytest.mark.scenario("SC-108")
def test_sc108_ensure_schema_once_runs_once_per_process(
    monkeypatch, clean_bootstrap_caches
) -> None:
    conn = _RecordingConnection()
    monkeypatch.setattr(bootstrap, "get_connection", _FakeConnectionFactory(conn))

    assert bootstrap.ensure_schema_once() is True
    count = len(conn.statements)
    assert bootstrap.ensure_schema_once() is True

    assert len(conn.statements) == count


@pytest.mark.scenario("SC-109")
def test_sc109_stale_probe_reconnects_without_rebuilding_schema_and_logs_warning(
    monkeypatch, clean_bootstrap_caches, caplog
) -> None:
    """連線失效：換新連線再探測，新連線上沒有任何 CREATE TABLE；記 WARNING 並標示已重連。"""
    dead = _RecordingConnection(stale_on_select_1=True)
    fresh = _RecordingConnection()
    factory = _FakeConnectionFactory(dead, fresh)
    monkeypatch.setattr(bootstrap, "get_connection", factory)
    # 以真實 cache_resource 的 clear 取代連線層的清除，模擬 get_connection.clear 換連線
    monkeypatch.setattr(bootstrap.get_connection, "clear", factory.clear, raising=False)
    metrics = bootstrap.get_query_metrics()

    with caplog.at_level(logging.WARNING, logger="asset_lab"):
        container = bootstrap.get_resilient_container()

    assert factory.clear_count == 1
    assert _create_table_statements(fresh) == []
    assert fresh.statements == ["SELECT 1"]
    assert container.health_repo._conn._inner is fresh
    assert metrics.take().reconnected is True
    warnings = [
        r for r in caplog.records if r.levelno == logging.WARNING and r.name.startswith("asset_lab")
    ]
    assert len(warnings) == 1
    assert "連線失效已重連" in warnings[0].getMessage()


@pytest.mark.scenario("SC-109")
def test_sc109_reconnect_keeps_read_cache(monkeypatch, clean_bootstrap_caches) -> None:
    dead = _RecordingConnection(stale_on_select_1=True)
    fresh = _RecordingConnection()
    factory = _FakeConnectionFactory(dead, fresh)
    monkeypatch.setattr(bootstrap, "get_connection", factory)
    monkeypatch.setattr(bootstrap.get_connection, "clear", factory.clear, raising=False)
    cache = bootstrap.get_read_cache()
    cache.put(("SELECT 1", ()), [(1,)], generation=cache.generation())

    bootstrap.get_resilient_container()

    assert cache.get(("SELECT 1", ())) == [(1,)]
    assert bootstrap.get_read_cache() is cache


@pytest.mark.scenario("SC-108")
def test_sc108_build_container_wires_health_repo_to_counted_layer_not_cached() -> None:
    conn = _FakeConnection()

    container = bootstrap.build_container(
        conn=conn, read_cache=ReadCache(ttl_seconds=300), query_metrics=QueryMetrics()
    )

    assert isinstance(container.health_repo, ConnectionHealthRepository)
    assert isinstance(container.health_repo._conn, CountingConnection)
    assert container.health_repo._conn._inner is conn
    assert container.health_repo._conn is container.schema_repo._conn


@pytest.mark.scenario("SC-108")
def test_sc108_ping_executes_select_1_through_the_connection() -> None:
    conn = _RecordingConnection()

    ConnectionHealthRepository(conn=conn).ping()

    assert conn.statements == ["SELECT 1"]


@pytest.mark.scenario("SC-109")
def test_sc109_ping_propagates_connection_error_unchanged() -> None:
    conn = _RecordingConnection(stale_on_select_1=True)

    with pytest.raises(ValueError, match="stream not found"):
        ConnectionHealthRepository(conn=conn).ping()


@pytest.mark.scenario("SC-108")
def test_sc108_ping_is_never_served_from_cache() -> None:
    """探測走計數層：即使快取裡有 SELECT 1，每次 ping 仍真的打到資料庫。"""
    conn = _RecordingConnection()
    metrics = QueryMetrics()
    container = bootstrap.build_container(
        conn=conn, read_cache=ReadCache(ttl_seconds=300), query_metrics=metrics
    )

    container.health_repo.ping()
    container.health_repo.ping()

    assert conn.statements == ["SELECT 1", "SELECT 1"]
    assert metrics.take().db_roundtrips >= 2


def test_is_stale_stream_error_matches_stream_not_found_message() -> None:
    """訊息含 stream not found（含大小寫混合）判定為可重連的連線失效。"""
    exc = ValueError('Hrana: `api error: `status=404, body={"error":"Stream Not Found: x"}``')

    assert bootstrap._is_stale_stream_error(exc) is True


def test_is_stale_stream_error_rejects_unrelated_business_error() -> None:
    """一般業務例外訊息（無 stream not found 字樣）判定為不可重連，避免誤吞。"""
    exc = ValueError("UNIQUE constraint failed: holdings.name")

    assert bootstrap._is_stale_stream_error(exc) is False


def test_secrets_template_keeps_allowed_emails_at_top_level() -> None:
    """secrets.toml.example 的 allowed_emails 須為頂層 key，不得落入任何 [section]。

    回歸防呆：allowed_emails 一旦被放在兩個 [section] 標頭之間，TOML 會把它歸入前一個
    區塊（例如 turso.allowed_emails），allowed_emails() 讀的頂層值即變 None，
    守門因而 fail-closed 擋下所有人（含合法使用者）。
    """
    template_path = APP_DIR / ".streamlit" / "secrets.toml.example"

    with template_path.open("rb") as f:
        parsed = tomllib.load(f)

    assert "allowed_emails" in parsed
    assert "allowed_emails" not in parsed.get("turso", {})
    assert "allowed_emails" not in parsed.get("auth", {})


def _arrow_memory_pool_setdefault_call(node: ast.stmt) -> ast.Call | None:
    """若此頂層敘述是 `os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", ...)` 則回傳該呼叫。"""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return None
    call = node.value
    func = call.func
    is_environ_setdefault = (
        isinstance(func, ast.Attribute)
        and func.attr == "setdefault"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
    )
    if not is_environ_setdefault:
        return None
    targets_arrow_key = any(
        isinstance(arg, ast.Constant) and arg.value == "ARROW_DEFAULT_MEMORY_POOL"
        for arg in call.args
    )
    return call if targets_arrow_key else None


def _is_streamlit_import(node: ast.stmt) -> bool:
    return isinstance(node, ast.Import) and any(alias.name == "streamlit" for alias in node.names)


def test_app_disables_pyarrow_mimalloc_before_importing_streamlit() -> None:
    """app.py 須在 import streamlit 之前，把 ARROW_DEFAULT_MEMORY_POOL 設為 system。

    回歸防呆：pyarrow 25 內建的 mimalloc 配置器在 macOS arm64 有 thread-init segfault，
    Streamlit 顯示 DataFrame（st.dataframe / st.data_editor）觸發 pandas→Arrow 轉換時，
    使用者本機操作（編輯月度錄入、切頁）曾實測整個 Python 進程 EXC_BAD_ACCESS 崩潰。
    設 ARROW_DEFAULT_MEMORY_POOL=system 停用 mimalloc、改用系統 malloc 已驗證可規避，
    但 pyarrow 只在自身被 import 的當下讀取此環境變數一次——而 Streamlit 一 import 就
    連帶 import pyarrow，因此這行必須在 `import streamlit` 之前執行才有效、且值須為
    "system"。segfault 本身難以在單元測試重現，故改以原始碼層級（AST）鎖定兩者的先後
    順序與設定值，避免日後有人不知情把 import 重新排序或誤刪這行、誤改值。
    """
    app_path = APP_DIR / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"), filename=str(app_path))

    setdefault_calls = [
        (node.lineno, call)
        for node in tree.body
        if (call := _arrow_memory_pool_setdefault_call(node)) is not None
    ]
    streamlit_import_lines = [node.lineno for node in tree.body if _is_streamlit_import(node)]

    assert setdefault_calls, "app.py 應設定 os.environ.setdefault('ARROW_DEFAULT_MEMORY_POOL', ...)"
    assert streamlit_import_lines, "app.py 應 import streamlit"

    setdefault_line, call = setdefault_calls[0]
    assert setdefault_line < streamlit_import_lines[0], (
        "ARROW_DEFAULT_MEMORY_POOL 必須在 import streamlit 之前設定，"
        "否則 pyarrow 已在 streamlit import 當下讀走舊值，設定不會生效"
    )
    assert call.args[1].value == "system", (
        "ARROW_DEFAULT_MEMORY_POOL 須設為 'system' 才會停用 mimalloc"
    )


# === logging 設定與頁面 logger 命名（SC-132） ===

_VIEWS_DIR = APP_DIR / "views"


@pytest.fixture
def isolated_logger():
    """測試專用 logger（不污染真正的 asset_lab）；結束後還原 handler 與 level。"""
    name = "asset_lab_test_logging"
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    yield logger
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)


@pytest.mark.scenario("SC-132")
def test_sc132_configure_logging_attaches_stderr_handler_with_level_and_format(
    isolated_logger,
) -> None:
    bootstrap.configure_logging(logger_name=isolated_logger.name, level="INFO", fmt="%(message)s")

    assert len(isolated_logger.handlers) == 1
    handler = isolated_logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert handler.formatter._fmt == "%(message)s"
    assert isolated_logger.level == logging.INFO
    # 不動 root、維持 propagate（既有 caplog 型測試依賴）
    assert isolated_logger.propagate is True


@pytest.mark.scenario("SC-132")
def test_sc132_configure_logging_is_idempotent(isolated_logger) -> None:
    for _ in range(3):
        bootstrap.configure_logging(
            logger_name=isolated_logger.name, level="INFO", fmt="%(message)s"
        )

    assert len(isolated_logger.handlers) == 1


@pytest.mark.scenario("SC-132")
def test_sc132_repeated_configure_emits_each_line_once(isolated_logger, capsys) -> None:
    for _ in range(3):
        bootstrap.configure_logging(
            logger_name=isolated_logger.name, level="INFO", fmt="%(message)s"
        )
    # handler 在 configure 時綁定 sys.stderr，capsys 已替換 → 可直接讀到輸出
    isolated_logger.info("一行")

    assert capsys.readouterr().err.count("一行") == 1


@pytest.mark.scenario("SC-132")
def test_sc132_info_level_is_not_dropped_for_child_loggers(isolated_logger, capsys) -> None:
    bootstrap.configure_logging(logger_name=isolated_logger.name, level="INFO", fmt="%(message)s")
    child = logging.getLogger(f"{isolated_logger.name}.views.input")

    child.info("資訊層級")

    assert "資訊層級" in capsys.readouterr().err


@pytest.mark.scenario("SC-132")
def test_sc132_ensure_logging_configured_uses_app_logging_constants() -> None:
    logger = logging.getLogger(APP_LOGGING.LOGGER_NAMESPACE)
    saved_handlers, saved_level = list(logger.handlers), logger.level
    logger.handlers.clear()
    try:
        bootstrap.ensure_logging_configured()
        bootstrap.ensure_logging_configured()

        assert len(logger.handlers) == 1
        assert logger.level == logging.getLevelName(APP_LOGGING.LEVEL)
        assert logger.handlers[0].formatter._fmt == APP_LOGGING.FORMAT
        assert logging.getLogger("asset_lab.views.input").isEnabledFor(logging.INFO)
    finally:
        logger.handlers[:] = saved_handlers
        logger.setLevel(saved_level)


@pytest.mark.scenario("SC-132")
def test_sc132_get_query_metrics_returns_one_shared_instance() -> None:
    bootstrap.get_query_metrics.clear()
    try:
        assert bootstrap.get_query_metrics() is bootstrap.get_query_metrics()
        assert isinstance(bootstrap.get_query_metrics(), QueryMetrics)
    finally:
        bootstrap.get_query_metrics.clear()


def _module_level_logger_names(path: Path) -> list[str]:
    """回傳頁面檔頂層 `logger = logging.getLogger("...")` 的名稱引數（字串常數才算）。"""
    names: list[str] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target, call = node.targets[0], node.value
        if not (isinstance(target, ast.Name) and target.id == "logger"):
            continue
        if isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.Constant):
            names.append(call.args[0].value)
    return names


@pytest.mark.scenario("SC-132")
def test_sc132_every_view_logger_is_named_after_its_file_under_asset_lab_views() -> None:
    view_files = sorted(_VIEWS_DIR.glob("*.py"))

    assert len(view_files) == 8
    for path in view_files:
        assert _module_level_logger_names(path) == [f"asset_lab.views.{path.stem}"], path.name


class TestSc116ClearReadCache:
    """SC-116：clear_read_cache 立即清掉程序級快取並記一行 log。"""

    @pytest.mark.scenario("SC-116")
    def test_sc116_clear_read_cache_empties_cache_and_logs(self, monkeypatch, caplog) -> None:
        cache = ReadCache(ttl_seconds=300)
        cache.put(("SELECT 1", ()), [(1,)], generation=cache.generation())
        monkeypatch.setattr(bootstrap, "get_read_cache", lambda: cache)

        with caplog.at_level(logging.INFO, logger="asset_lab"):
            bootstrap.clear_read_cache()

        assert cache.get(("SELECT 1", ())) is None
        records = [r for r in caplog.records if r.name.startswith("asset_lab")]
        assert len(records) == 1
        assert "read_cache_cleared" in records[0].getMessage()

    @pytest.mark.scenario("SC-116")
    def test_sc116_after_clear_next_read_comes_from_database(self) -> None:
        conn = libsql.connect(":memory:")
        SchemaRepository(conn=conn).ensure_schema()
        cache = ReadCache(ttl_seconds=300)
        container = bootstrap.build_container(
            conn=conn, read_cache=cache, query_metrics=QueryMetrics()
        )
        assert container.holding_repo.list_holdings() == []
        # 別處（另一條路徑）改了資料庫，這條連線的快取仍是舊的
        HoldingRepository(conn=conn).add_holding(
            holding=HoldingModel(
                name="別處新增",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.DEMAND_DEPOSIT,
                initial_market_value=1.0,
                initial_cost=1.0,
            )
        )
        assert container.holding_repo.list_holdings() == []

        cache.clear()

        assert [h.name for h in container.holding_repo.list_holdings()] == ["別處新增"]

    @pytest.mark.scenario("SC-116")
    def test_sc116_get_read_cache_uses_configured_ttl_and_survives_reconnect(self) -> None:
        bootstrap.get_read_cache.clear()
        first = bootstrap.get_read_cache()

        bootstrap.get_connection.clear()
        bootstrap.get_container.clear()

        assert bootstrap.get_read_cache() is first
        assert first._ttl_seconds == READ_CACHE.TTL_SECONDS
        bootstrap.get_read_cache.clear()
