"""回撤門檻設定 I/O。level 為主鍵；drawdown_threshold 以正回撤幅度百分比儲存。

只做 row↔ProtocolThresholdModel 轉換與 SQL 執行；門檻順序是否合法（0 < L1 < L2 < L3）
的業務校驗由上層 ProtocolService 負責，本層不判斷。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import PROTOCOL_THRESHOLDS_TABLE
from asset_lab.models.protocol import ProtocolThresholdModel

if TYPE_CHECKING:
    from libsql import Connection

_TABLE = PROTOCOL_THRESHOLDS_TABLE.TABLE_NAME
_LEVEL = PROTOCOL_THRESHOLDS_TABLE.LEVEL
_DRAWDOWN_THRESHOLD = PROTOCOL_THRESHOLDS_TABLE.DRAWDOWN_THRESHOLD

_SELECT_ALL = f"SELECT {_LEVEL}, {_DRAWDOWN_THRESHOLD} FROM {_TABLE} ORDER BY {_LEVEL}"
_UPSERT = (
    f"INSERT INTO {_TABLE} ({_LEVEL}, {_DRAWDOWN_THRESHOLD}) VALUES (?, ?) "
    f"ON CONFLICT({_LEVEL}) DO UPDATE SET {_DRAWDOWN_THRESHOLD} = excluded.{_DRAWDOWN_THRESHOLD}"
)


def _row_to_model(row: tuple) -> ProtocolThresholdModel:
    """把回撤門檻 row tuple 組回 ProtocolThresholdModel。"""
    level, drawdown_threshold = row
    return ProtocolThresholdModel(level=level, drawdown_threshold=drawdown_threshold)


class ProtocolThresholdRepository:
    """回撤門檻設定 I/O。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化回撤門檻 Repository。

        Args:
            conn: libsql 連線。
        """
        self._conn = conn

    def read_thresholds(self) -> list[ProtocolThresholdModel]:
        """讀全部已保存的回撤門檻，依等級排序（可能不完整，0～3 筆）。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_ALL)
        return [_row_to_model(row) for row in cursor.fetchall()]

    def upsert_threshold(self, *, threshold: ProtocolThresholdModel) -> None:
        """新增或更新某等級的回撤門檻（同等級存在則覆蓋）。"""
        cursor = self._conn.cursor()
        cursor.execute(_UPSERT, (threshold.level, threshold.drawdown_threshold))
        self._conn.commit()
