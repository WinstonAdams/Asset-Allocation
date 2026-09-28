"""建表 Repository——首次啟動建立六張表（if not exists），並將 holdings 加欄遷移到位。

六表結構與設計文件一致：
- holdings：持有項目主檔，holding_id 為自動遞增主鍵（穩定身分，改名不斷裂歷史）。
- monthly_records：項目 × 月份時間序列，(holding_id, year_month) 為複合主鍵（唯一鍵）。
- target_allocations：分類目標配置，category 為主鍵，目標比重以百分比儲存。
- protocol_thresholds：大跌行為協定回撤門檻設定，level 為主鍵，門檻以正幅度百分比儲存。
- house_params：買房參數設定，param_key 為主鍵，param_value 統一以 REAL 儲存。
- subjective_triggers：主觀觸發勾選狀態，trigger_key 為主鍵，checked 以 0/1 儲存。

本層只負責 DDL 執行（純 I/O），不含任何業務判斷。

holdings 的 purpose 欄、monthly_records 的 total_cost/realized_income 欄皆為既有已部署
資料庫的加欄演進：CREATE TABLE IF NOT EXISTS 對已存在的表是 no-op，無法讓已建表的舊庫
拿到新欄位，故另以 PRAGMA table_info 探測欄位是否已存在、缺才 ALTER TABLE 補上
（idempotent，重複呼叫安全，三欄共用同一 _add_column_if_missing helper）；全新資料庫則由
_CREATE_HOLDINGS / _CREATE_MONTHLY_RECORDS 直接建出含新欄的完整表，兩路徑最終結構一致。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import (
    HOLDING_PURPOSE,
    HOLDINGS_TABLE,
    HOUSE_PARAMS_TABLE,
    MONTHLY_RECORDS_TABLE,
    PROTOCOL_THRESHOLDS_TABLE,
    SUBJECTIVE_TRIGGERS_TABLE,
    TARGET_ALLOCATIONS_TABLE,
)

if TYPE_CHECKING:
    from libsql import Connection, Cursor


# 建立持有項目主檔。holding_id 自動遞增提供穩定身分；負債的 category/initial_* 留 NULL。
# purpose 為純附加用途標記，新庫直建即含此欄，預設一般（既有資料庫由下方加欄遷移補上）。
_CREATE_HOLDINGS = f"""
CREATE TABLE IF NOT EXISTS {HOLDINGS_TABLE.TABLE_NAME} (
    {HOLDINGS_TABLE.HOLDING_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
    {HOLDINGS_TABLE.NAME} TEXT NOT NULL,
    {HOLDINGS_TABLE.KIND} TEXT NOT NULL,
    {HOLDINGS_TABLE.CATEGORY} TEXT,
    {HOLDINGS_TABLE.INITIAL_MARKET_VALUE} REAL,
    {HOLDINGS_TABLE.INITIAL_COST} REAL,
    {HOLDINGS_TABLE.CREATED_AT} TEXT,
    {HOLDINGS_TABLE.PURPOSE} TEXT NOT NULL DEFAULT '{HOLDING_PURPOSE.GENERAL}'
)
"""

# 既有（本 Change 之前建立）的 holdings 表加欄遷移：DEFAULT 回填讓既有列自動視為一般用途。
_ALTER_HOLDINGS_ADD_PURPOSE = (
    f"ALTER TABLE {HOLDINGS_TABLE.TABLE_NAME} ADD COLUMN "
    f"{HOLDINGS_TABLE.PURPOSE} TEXT NOT NULL DEFAULT '{HOLDING_PURPOSE.GENERAL}'"
)

# 既有（本功能上線前建立）的 monthly_records 表加欄遷移：不設 DEFAULT，既有列補 NULL
# （＝舊制列），與新庫直建的 NULL 語意一致。
_ALTER_MONTHLY_RECORDS_ADD_TOTAL_COST = (
    f"ALTER TABLE {MONTHLY_RECORDS_TABLE.TABLE_NAME} ADD COLUMN "
    f"{MONTHLY_RECORDS_TABLE.TOTAL_COST} REAL"
)
_ALTER_MONTHLY_RECORDS_ADD_REALIZED_INCOME = (
    f"ALTER TABLE {MONTHLY_RECORDS_TABLE.TABLE_NAME} ADD COLUMN "
    f"{MONTHLY_RECORDS_TABLE.REALIZED_INCOME} REAL"
)

# 月度時間序列。複合主鍵 (holding_id, year_month) 由 DB 保證同月同項目不得有兩列。
# total_cost/realized_income 為股票/ETF 總成本推算功能附加欄位，皆可為 NULL、不設 DEFAULT：
# NULL 本身就代表「非股票/ETF 或本功能上線前的舊制列」，新庫直建即含此二欄（既有資料庫由
# 下方加欄遷移補上）。
_CREATE_MONTHLY_RECORDS = f"""
CREATE TABLE IF NOT EXISTS {MONTHLY_RECORDS_TABLE.TABLE_NAME} (
    {MONTHLY_RECORDS_TABLE.HOLDING_ID} INTEGER NOT NULL,
    {MONTHLY_RECORDS_TABLE.YEAR_MONTH} TEXT NOT NULL,
    {MONTHLY_RECORDS_TABLE.MARKET_VALUE} REAL,
    {MONTHLY_RECORDS_TABLE.NET_INVESTMENT} REAL NOT NULL DEFAULT 0,
    {MONTHLY_RECORDS_TABLE.TOTAL_COST} REAL,
    {MONTHLY_RECORDS_TABLE.REALIZED_INCOME} REAL,
    PRIMARY KEY ({MONTHLY_RECORDS_TABLE.HOLDING_ID}, {MONTHLY_RECORDS_TABLE.YEAR_MONTH})
)
"""

# 分類目標配置。category 為主鍵；target_weight 以百分比（0–100）儲存。
_CREATE_TARGET_ALLOCATIONS = f"""
CREATE TABLE IF NOT EXISTS {TARGET_ALLOCATIONS_TABLE.TABLE_NAME} (
    {TARGET_ALLOCATIONS_TABLE.CATEGORY} TEXT PRIMARY KEY,
    {TARGET_ALLOCATIONS_TABLE.TARGET_WEIGHT} REAL NOT NULL
)
"""

# 大跌行為協定回撤門檻設定。level 為主鍵；drawdown_threshold 為正回撤幅度百分比。
_CREATE_PROTOCOL_THRESHOLDS = f"""
CREATE TABLE IF NOT EXISTS {PROTOCOL_THRESHOLDS_TABLE.TABLE_NAME} (
    {PROTOCOL_THRESHOLDS_TABLE.LEVEL} TEXT PRIMARY KEY,
    {PROTOCOL_THRESHOLDS_TABLE.DRAWDOWN_THRESHOLD} REAL NOT NULL
)
"""

# 買房參數設定。param_key 為主鍵；param_value 統一以 REAL 儲存（含比率、金額、年份）。
_CREATE_HOUSE_PARAMS = f"""
CREATE TABLE IF NOT EXISTS {HOUSE_PARAMS_TABLE.TABLE_NAME} (
    {HOUSE_PARAMS_TABLE.PARAM_KEY} TEXT PRIMARY KEY,
    {HOUSE_PARAMS_TABLE.PARAM_VALUE} REAL NOT NULL
)
"""

# 主觀觸發勾選狀態。trigger_key 為主鍵；checked 以 0/1 儲存，未存在的鍵視同未勾選。
_CREATE_SUBJECTIVE_TRIGGERS = f"""
CREATE TABLE IF NOT EXISTS {SUBJECTIVE_TRIGGERS_TABLE.TABLE_NAME} (
    {SUBJECTIVE_TRIGGERS_TABLE.TRIGGER_KEY} TEXT PRIMARY KEY,
    {SUBJECTIVE_TRIGGERS_TABLE.CHECKED} INTEGER NOT NULL DEFAULT 0
)
"""


class SchemaRepository:
    """建表：首次啟動建立六張表（if not exists）並補齊 holdings 加欄遷移。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化建表 Repository。

        Args:
            conn: libsql 連線；測試以記憶體 DB 注入，正式以 Turso 連線注入。
        """
        self._conn = conn

    def ensure_schema(self) -> None:
        """建立六張表（if not exists）並補齊 holdings / monthly_records 加欄遷移。

        重複呼叫安全（idempotent），不影響既有資料：建表為 CREATE IF NOT EXISTS，
        加欄遷移先探測欄位是否已存在，缺才 ALTER，避免對已升級過的庫重複 ALTER 出錯。
        """
        cursor = self._conn.cursor()
        cursor.execute(_CREATE_HOLDINGS)
        cursor.execute(_CREATE_MONTHLY_RECORDS)
        cursor.execute(_CREATE_TARGET_ALLOCATIONS)
        cursor.execute(_CREATE_PROTOCOL_THRESHOLDS)
        cursor.execute(_CREATE_HOUSE_PARAMS)
        cursor.execute(_CREATE_SUBJECTIVE_TRIGGERS)
        self._add_column_if_missing(
            cursor,
            table=HOLDINGS_TABLE.TABLE_NAME,
            column=HOLDINGS_TABLE.PURPOSE,
            alter_sql=_ALTER_HOLDINGS_ADD_PURPOSE,
        )
        self._add_column_if_missing(
            cursor,
            table=MONTHLY_RECORDS_TABLE.TABLE_NAME,
            column=MONTHLY_RECORDS_TABLE.TOTAL_COST,
            alter_sql=_ALTER_MONTHLY_RECORDS_ADD_TOTAL_COST,
        )
        self._add_column_if_missing(
            cursor,
            table=MONTHLY_RECORDS_TABLE.TABLE_NAME,
            column=MONTHLY_RECORDS_TABLE.REALIZED_INCOME,
            alter_sql=_ALTER_MONTHLY_RECORDS_ADD_REALIZED_INCOME,
        )
        self._conn.commit()

    @staticmethod
    def _add_column_if_missing(
        cursor: "Cursor", *, table: str, column: str, alter_sql: str
    ) -> None:
        """加欄遷移通用 helper：PRAGMA 探測欄位是否已存在，缺才執行 alter_sql 補上。

        全新資料庫已由對應的 CREATE TABLE 直接建出該欄，此處探測必為已存在、略過
        ALTER；本 Change（或更早）之前建立的既有資料庫探測不到該欄，才執行 ALTER 加欄，
        既有列不遺失也不變動（idempotent，重複呼叫安全）。
        """
        cursor.execute(f"PRAGMA table_info({table})")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if column not in existing_columns:
            cursor.execute(alter_sql)
