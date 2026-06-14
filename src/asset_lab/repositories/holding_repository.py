"""持有項目主檔 I/O。

只做 row↔HoldingModel 轉換與 SQL 執行，不含業務判斷（資產/負債的語意解讀、分類合法性
皆由上層負責）。holding_id 為 DB 自動遞增的穩定身分：改名（update_holding 改 name）或
改分類（update_holding 改 category）都不更動 holding_id，故歷史月度紀錄恆掛在同一身分上、
連乘不斷裂；分類只存於主檔當前值，無逐月版本（回溯佔比以當前分類重算）。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import HOLDINGS_TABLE
from asset_lab.models.holding import HoldingModel

if TYPE_CHECKING:
    from libsql import Connection

# 主檔欄位讀取順序；row tuple 依此順序對映回 HoldingModel。
_COLUMNS = (
    HOLDINGS_TABLE.HOLDING_ID,
    HOLDINGS_TABLE.NAME,
    HOLDINGS_TABLE.KIND,
    HOLDINGS_TABLE.CATEGORY,
    HOLDINGS_TABLE.INITIAL_MARKET_VALUE,
    HOLDINGS_TABLE.INITIAL_COST,
)
_SELECT_COLUMNS = ", ".join(_COLUMNS)

_SELECT_ALL = (
    f"SELECT {_SELECT_COLUMNS} FROM {HOLDINGS_TABLE.TABLE_NAME} "
    f"ORDER BY {HOLDINGS_TABLE.HOLDING_ID}"
)
_SELECT_ONE = (
    f"SELECT {_SELECT_COLUMNS} FROM {HOLDINGS_TABLE.TABLE_NAME} "
    f"WHERE {HOLDINGS_TABLE.HOLDING_ID} = ?"
)
_INSERT = (
    f"INSERT INTO {HOLDINGS_TABLE.TABLE_NAME} "
    f"({HOLDINGS_TABLE.NAME}, {HOLDINGS_TABLE.KIND}, {HOLDINGS_TABLE.CATEGORY}, "
    f"{HOLDINGS_TABLE.INITIAL_MARKET_VALUE}, {HOLDINGS_TABLE.INITIAL_COST}, "
    f"{HOLDINGS_TABLE.CREATED_AT}) VALUES (?, ?, ?, ?, ?, ?)"
)
_UPDATE = (
    f"UPDATE {HOLDINGS_TABLE.TABLE_NAME} SET "
    f"{HOLDINGS_TABLE.NAME} = ?, {HOLDINGS_TABLE.KIND} = ?, {HOLDINGS_TABLE.CATEGORY} = ?, "
    f"{HOLDINGS_TABLE.INITIAL_MARKET_VALUE} = ?, {HOLDINGS_TABLE.INITIAL_COST} = ? "
    f"WHERE {HOLDINGS_TABLE.HOLDING_ID} = ?"
)
_DELETE_ALL = f"DELETE FROM {HOLDINGS_TABLE.TABLE_NAME}"


def _row_to_model(row: tuple) -> HoldingModel:
    """把主檔 row tuple 依固定欄序組回 HoldingModel。"""
    holding_id, name, kind, category, initial_market_value, initial_cost = row
    return HoldingModel(
        holding_id=holding_id,
        name=name,
        kind=kind,
        category=category,
        initial_market_value=initial_market_value,
        initial_cost=initial_cost,
    )


class HoldingRepository:
    """持有項目主檔 I/O。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化主檔 Repository。

        Args:
            conn: libsql 連線。
        """
        self._conn = conn

    def list_holdings(self) -> list[HoldingModel]:
        """列出全部主檔項目，依 holding_id 遞增排序。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_ALL)
        return [_row_to_model(row) for row in cursor.fetchall()]

    def get_holding(self, *, holding_id: int) -> HoldingModel | None:
        """依穩定身分取單一項目；不存在回 None。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_ONE, (holding_id,))
        row = cursor.fetchone()
        return _row_to_model(row) if row is not None else None

    def add_holding(self, *, holding: HoldingModel, created_at: str | None = None) -> int:
        """新增一筆主檔，回傳 DB 產生的穩定 holding_id。

        Args:
            holding: 待新增項目（holding_id 由 DB 產生，傳入值忽略）。
            created_at: 建立時間戳（ISO 字串）；未提供則存 NULL。

        Returns:
            新項目的 holding_id。
        """
        cursor = self._conn.cursor()
        cursor.execute(
            _INSERT,
            (
                holding.name,
                holding.kind,
                holding.category,
                holding.initial_market_value,
                holding.initial_cost,
                created_at,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def update_holding(self, *, holding: HoldingModel) -> None:
        """更新既有項目（改名 / 改分類 / 改初始值）。holding_id 不變，歷史紀錄不斷裂。"""
        cursor = self._conn.cursor()
        cursor.execute(
            _UPDATE,
            (
                holding.name,
                holding.kind,
                holding.category,
                holding.initial_market_value,
                holding.initial_cost,
                holding.holding_id,
            ),
        )
        self._conn.commit()

    def replace_all(self, *, holdings: list[HoldingModel]) -> None:
        """清空主檔後批次寫入（CSV 匯入用）。保留來源 holding_id 以維持紀錄對映。"""
        cursor = self._conn.cursor()
        cursor.execute(_DELETE_ALL)
        for holding in holdings:
            cursor.execute(
                f"INSERT INTO {HOLDINGS_TABLE.TABLE_NAME} "
                f"({HOLDINGS_TABLE.HOLDING_ID}, {HOLDINGS_TABLE.NAME}, {HOLDINGS_TABLE.KIND}, "
                f"{HOLDINGS_TABLE.CATEGORY}, {HOLDINGS_TABLE.INITIAL_MARKET_VALUE}, "
                f"{HOLDINGS_TABLE.INITIAL_COST}) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    holding.holding_id,
                    holding.name,
                    holding.kind,
                    holding.category,
                    holding.initial_market_value,
                    holding.initial_cost,
                ),
            )
        self._conn.commit()
