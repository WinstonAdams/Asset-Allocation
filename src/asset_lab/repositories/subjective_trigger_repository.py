"""主觀觸發勾選狀態 I/O。trigger_key 為主鍵；checked 以 0/1 儲存、還原為 bool。

只做 row↔SubjectiveTriggerModel 轉換與 SQL 執行；「資料庫無紀錄視同未勾選」的業務
語意由消費此 Repository 的呼叫端解讀，本層只回傳實際已存在的列。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import SUBJECTIVE_TRIGGERS_TABLE
from asset_lab.models.house import SubjectiveTriggerModel

if TYPE_CHECKING:
    from libsql import Connection

_TABLE = SUBJECTIVE_TRIGGERS_TABLE.TABLE_NAME
_TRIGGER_KEY = SUBJECTIVE_TRIGGERS_TABLE.TRIGGER_KEY
_CHECKED = SUBJECTIVE_TRIGGERS_TABLE.CHECKED

_SELECT_ALL = f"SELECT {_TRIGGER_KEY}, {_CHECKED} FROM {_TABLE}"
_UPSERT = (
    f"INSERT INTO {_TABLE} ({_TRIGGER_KEY}, {_CHECKED}) VALUES (?, ?) "
    f"ON CONFLICT({_TRIGGER_KEY}) DO UPDATE SET {_CHECKED} = excluded.{_CHECKED}"
)


def _row_to_model(row: tuple) -> SubjectiveTriggerModel:
    """把主觀觸發 row tuple 組回 SubjectiveTriggerModel（0/1 還原為 bool）。"""
    trigger_key, checked = row
    return SubjectiveTriggerModel(trigger_key=trigger_key, checked=bool(checked))


class SubjectiveTriggerRepository:
    """主觀觸發勾選狀態 I/O。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化主觀觸發 Repository。

        Args:
            conn: libsql 連線。
        """
        self._conn = conn

    def read_triggers(self) -> list[SubjectiveTriggerModel]:
        """讀全部已保存的主觀觸發勾選狀態，可能不完整（0～2 筆，任意順序）。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_ALL)
        return [_row_to_model(row) for row in cursor.fetchall()]

    def upsert_trigger(self, *, trigger: SubjectiveTriggerModel) -> None:
        """新增或更新某主觀觸發鍵的勾選狀態（同鍵存在則覆蓋）。"""
        cursor = self._conn.cursor()
        cursor.execute(_UPSERT, (trigger.trigger_key, int(trigger.checked)))
        self._conn.commit()
