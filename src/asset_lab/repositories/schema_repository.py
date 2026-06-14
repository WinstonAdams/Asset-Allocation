"""建表 Repository——首次啟動建立三張表（if not exists）。

三表結構與設計文件一致：
- holdings：持有項目主檔，holding_id 為自動遞增主鍵（穩定身分，改名不斷裂歷史）。
- monthly_records：項目 × 月份時間序列，(holding_id, year_month) 為複合主鍵（唯一鍵）。
- target_allocations：分類目標配置，category 為主鍵，目標比重以百分比儲存。

本層只負責 DDL 執行（純 I/O），不含任何業務判斷。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import (
    HOLDINGS_TABLE,
    MONTHLY_RECORDS_TABLE,
    TARGET_ALLOCATIONS_TABLE,
)

if TYPE_CHECKING:
    from libsql import Connection


# 建立持有項目主檔。holding_id 自動遞增提供穩定身分；負債的 category/initial_* 留 NULL。
_CREATE_HOLDINGS = f"""
CREATE TABLE IF NOT EXISTS {HOLDINGS_TABLE.TABLE_NAME} (
    {HOLDINGS_TABLE.HOLDING_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
    {HOLDINGS_TABLE.NAME} TEXT NOT NULL,
    {HOLDINGS_TABLE.KIND} TEXT NOT NULL,
    {HOLDINGS_TABLE.CATEGORY} TEXT,
    {HOLDINGS_TABLE.INITIAL_MARKET_VALUE} REAL,
    {HOLDINGS_TABLE.INITIAL_COST} REAL,
    {HOLDINGS_TABLE.CREATED_AT} TEXT
)
"""

# 月度時間序列。複合主鍵 (holding_id, year_month) 由 DB 保證同月同項目不得有兩列。
_CREATE_MONTHLY_RECORDS = f"""
CREATE TABLE IF NOT EXISTS {MONTHLY_RECORDS_TABLE.TABLE_NAME} (
    {MONTHLY_RECORDS_TABLE.HOLDING_ID} INTEGER NOT NULL,
    {MONTHLY_RECORDS_TABLE.YEAR_MONTH} TEXT NOT NULL,
    {MONTHLY_RECORDS_TABLE.MARKET_VALUE} REAL,
    {MONTHLY_RECORDS_TABLE.NET_INVESTMENT} REAL NOT NULL DEFAULT 0,
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


class SchemaRepository:
    """建表：首次啟動建立三張表（if not exists）。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化建表 Repository。

        Args:
            conn: libsql 連線；測試以記憶體 DB 注入，正式以 Turso 連線注入。
        """
        self._conn = conn

    def ensure_schema(self) -> None:
        """建立三張表（if not exists）。重複呼叫安全（idempotent），不影響既有資料。"""
        cursor = self._conn.cursor()
        cursor.execute(_CREATE_HOLDINGS)
        cursor.execute(_CREATE_MONTHLY_RECORDS)
        cursor.execute(_CREATE_TARGET_ALLOCATIONS)
        self._conn.commit()
