"""買房參數設定 I/O。param_key 為主鍵；param_value 統一以 REAL 儲存。

只做 row↔HouseParamModel 轉換與 SQL 執行；缺鍵補中性預設、型別還原（如 target_year
轉 int）等業務規則由上層 HouseService 負責，本層不判斷。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import HOUSE_PARAMS_TABLE
from asset_lab.models.house import HouseParamModel

if TYPE_CHECKING:
    from libsql import Connection

_TABLE = HOUSE_PARAMS_TABLE.TABLE_NAME
_PARAM_KEY = HOUSE_PARAMS_TABLE.PARAM_KEY
_PARAM_VALUE = HOUSE_PARAMS_TABLE.PARAM_VALUE

_SELECT_ALL = f"SELECT {_PARAM_KEY}, {_PARAM_VALUE} FROM {_TABLE}"
_UPSERT = (
    f"INSERT INTO {_TABLE} ({_PARAM_KEY}, {_PARAM_VALUE}) VALUES (?, ?) "
    f"ON CONFLICT({_PARAM_KEY}) DO UPDATE SET {_PARAM_VALUE} = excluded.{_PARAM_VALUE}"
)


def _row_to_model(row: tuple) -> HouseParamModel:
    """把買房參數 row tuple 組回 HouseParamModel。"""
    param_key, param_value = row
    return HouseParamModel(param_key=param_key, param_value=param_value)


class HouseParamRepository:
    """買房參數設定 I/O。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化買房參數 Repository。

        Args:
            conn: libsql 連線。
        """
        self._conn = conn

    def read_params(self) -> list[HouseParamModel]:
        """讀全部已保存的買房參數，可能不完整（0～9 筆，任意順序）。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_ALL)
        return [_row_to_model(row) for row in cursor.fetchall()]

    def upsert_param(self, *, param: HouseParamModel) -> None:
        """新增或更新某參數鍵的值（同鍵存在則覆蓋）。"""
        cursor = self._conn.cursor()
        cursor.execute(_UPSERT, (param.param_key, param.param_value))
        self._conn.commit()
