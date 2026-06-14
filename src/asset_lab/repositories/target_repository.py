"""分類目標配置 I/O。category 為主鍵；target_weight 以百分比（0–100）儲存。

只做 row↔TargetAllocationModel 轉換與 SQL 執行；目標總和是否為 100% 的業務校驗由上層
（DataIoService / Page）負責，本層不判斷。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import TARGET_ALLOCATIONS_TABLE
from asset_lab.models.target import TargetAllocationModel

if TYPE_CHECKING:
    from libsql import Connection

_TABLE = TARGET_ALLOCATIONS_TABLE.TABLE_NAME
_CATEGORY = TARGET_ALLOCATIONS_TABLE.CATEGORY
_TARGET_WEIGHT = TARGET_ALLOCATIONS_TABLE.TARGET_WEIGHT

_SELECT_ALL = f"SELECT {_CATEGORY}, {_TARGET_WEIGHT} FROM {_TABLE} ORDER BY {_CATEGORY}"
_UPSERT = (
    f"INSERT INTO {_TABLE} ({_CATEGORY}, {_TARGET_WEIGHT}) VALUES (?, ?) "
    f"ON CONFLICT({_CATEGORY}) DO UPDATE SET {_TARGET_WEIGHT} = excluded.{_TARGET_WEIGHT}"
)


def _row_to_model(row: tuple) -> TargetAllocationModel:
    """把目標配置 row tuple 組回 TargetAllocationModel。"""
    category, target_weight = row
    return TargetAllocationModel(category=category, target_weight=target_weight)


class TargetRepository:
    """分類目標配置 I/O。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化目標配置 Repository。

        Args:
            conn: libsql 連線。
        """
        self._conn = conn

    def read_targets(self) -> list[TargetAllocationModel]:
        """讀全部分類目標配置，依分類排序。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_ALL)
        return [_row_to_model(row) for row in cursor.fetchall()]

    def upsert_target(self, *, target: TargetAllocationModel) -> None:
        """新增或更新某分類的目標比重（同分類存在則覆蓋）。"""
        cursor = self._conn.cursor()
        cursor.execute(_UPSERT, (target.category, target.target_weight))
        self._conn.commit()

    def read_all(self) -> list[TargetAllocationModel]:
        """讀全部目標配置（CSV 匯出用）；與 read_targets 同結果。"""
        return self.read_targets()
