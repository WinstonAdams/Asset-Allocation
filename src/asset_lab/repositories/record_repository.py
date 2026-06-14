"""月度紀錄 I/O。(holding_id, year_month) 為複合主鍵（唯一鍵）。

兩條寫入路徑語意不同：
- insert_record：嚴格新增，同月同項目已存在時拒絕（不覆蓋既有列）；對應「新增一列」操作。
- upsert_record：存在則更新、不存在則新增；對應「編輯既有列」操作（不產生重複列）。

唯一鍵由 DB 的複合主鍵保證。libsql 在違反唯一約束時以一般 ValueError 拋出（訊息含
"UNIQUE constraint failed"），且錯誤發生在 execute 當下、既有列不被更動；本層只把這個
特定的唯一鍵衝突轉譯為領域例外 DataValidationError，讓上層能與其他 I/O 錯誤區分，其餘
錯誤原樣往上拋。

報酬率/趨勢/匯出用的區間與全量讀取以 DataFrame 回傳，方便 Service 端做連乘與彙總。
"""

# ==== 原生（標準庫） ====
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import MONTHLY_RECORDS_TABLE
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.record import MonthlyRecordModel

if TYPE_CHECKING:
    from libsql import Connection

# libsql 對唯一約束衝突拋出的 ValueError 訊息片段。
_UNIQUE_VIOLATION_MARKER = "UNIQUE constraint failed"

_COLUMNS = (
    MONTHLY_RECORDS_TABLE.HOLDING_ID,
    MONTHLY_RECORDS_TABLE.YEAR_MONTH,
    MONTHLY_RECORDS_TABLE.MARKET_VALUE,
    MONTHLY_RECORDS_TABLE.NET_INVESTMENT,
)
_SELECT_COLUMNS = ", ".join(_COLUMNS)
_TABLE = MONTHLY_RECORDS_TABLE.TABLE_NAME
_HOLDING_ID = MONTHLY_RECORDS_TABLE.HOLDING_ID
_YEAR_MONTH = MONTHLY_RECORDS_TABLE.YEAR_MONTH
_MARKET_VALUE = MONTHLY_RECORDS_TABLE.MARKET_VALUE
_NET_INVESTMENT = MONTHLY_RECORDS_TABLE.NET_INVESTMENT

_SELECT_MONTH = (
    f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} WHERE {_YEAR_MONTH} = ? ORDER BY {_HOLDING_ID}"
)
_SELECT_RANGE = (
    f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} WHERE {_YEAR_MONTH} BETWEEN ? AND ? "
    f"ORDER BY {_YEAR_MONTH}, {_HOLDING_ID}"
)
_SELECT_ALL = f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} ORDER BY {_YEAR_MONTH}, {_HOLDING_ID}"
_SELECT_LATEST = f"SELECT MAX({_YEAR_MONTH}) FROM {_TABLE}"
_INSERT = (
    f"INSERT INTO {_TABLE} ({_HOLDING_ID}, {_YEAR_MONTH}, {_MARKET_VALUE}, {_NET_INVESTMENT}) "
    f"VALUES (?, ?, ?, ?)"
)
_UPSERT = (
    f"INSERT INTO {_TABLE} ({_HOLDING_ID}, {_YEAR_MONTH}, {_MARKET_VALUE}, {_NET_INVESTMENT}) "
    f"VALUES (?, ?, ?, ?) "
    f"ON CONFLICT({_HOLDING_ID}, {_YEAR_MONTH}) DO UPDATE SET "
    f"{_MARKET_VALUE} = excluded.{_MARKET_VALUE}, "
    f"{_NET_INVESTMENT} = excluded.{_NET_INVESTMENT}"
)
_DELETE_ONE = f"DELETE FROM {_TABLE} WHERE {_HOLDING_ID} = ? AND {_YEAR_MONTH} = ?"
_DELETE_ALL = f"DELETE FROM {_TABLE}"


def _row_to_model(row: tuple) -> MonthlyRecordModel:
    """把月度 row tuple 依固定欄序組回 MonthlyRecordModel。"""
    holding_id, year_month, market_value, net_investment = row
    return MonthlyRecordModel(
        holding_id=holding_id,
        year_month=year_month,
        market_value=market_value,
        net_investment=net_investment,
    )


def _values(record: MonthlyRecordModel) -> tuple:
    """把 MonthlyRecordModel 攤平成寫入參數（依插入欄序）。"""
    return (record.holding_id, record.year_month, record.market_value, record.net_investment)


class RecordRepository:
    """月度紀錄 I/O。(holding_id, year_month) 為唯一鍵。連線由 bootstrap 注入。"""

    def __init__(self, *, conn: "Connection") -> None:
        """初始化月度紀錄 Repository。

        Args:
            conn: libsql 連線。
        """
        self._conn = conn

    def read_month(self, *, year_month: str) -> list[MonthlyRecordModel]:
        """讀某月份全部項目紀錄，依 holding_id 排序。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_MONTH, (year_month,))
        return [_row_to_model(row) for row in cursor.fetchall()]

    def read_range(self, *, start_ym: str, end_ym: str) -> pd.DataFrame:
        """讀區間內（含端點）全部紀錄為 DataFrame，供報酬率連乘/趨勢使用。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_RANGE, (start_ym, end_ym))
        return self._to_dataframe(cursor.fetchall())

    def read_all(self) -> pd.DataFrame:
        """讀全部紀錄為 DataFrame，供 CSV 匯出使用。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_ALL)
        return self._to_dataframe(cursor.fetchall())

    def latest_year_month(self) -> str | None:
        """回傳最新有資料的月份；無任何紀錄時回 None（供帶入上月判斷）。"""
        cursor = self._conn.cursor()
        cursor.execute(_SELECT_LATEST)
        row = cursor.fetchone()
        return row[0] if row is not None and row[0] is not None else None

    def insert_record(self, *, record: MonthlyRecordModel) -> None:
        """嚴格新增單列；同月同項目已存在時拒絕（不覆蓋既有列）。

        Raises:
            DataValidationError: 同 (holding_id, year_month) 紀錄已存在（違反唯一鍵）。
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(_INSERT, _values(record))
        except ValueError as error:
            # 同月同項目不可有兩列：把唯一鍵衝突轉成領域例外，其餘錯誤原樣往上拋
            if _UNIQUE_VIOLATION_MARKER in str(error):
                raise DataValidationError(
                    f"同月同項目已有紀錄，不可重複建立："
                    f"({record.holding_id}, {record.year_month})"
                ) from error
            raise
        self._conn.commit()

    def upsert_record(self, *, record: MonthlyRecordModel) -> None:
        """新增或更新單列：同 (holding_id, year_month) 存在則更新、不存在則新增。"""
        cursor = self._conn.cursor()
        cursor.execute(_UPSERT, _values(record))
        self._conn.commit()

    def delete_record(self, *, holding_id: int, year_month: str) -> None:
        """刪除某 (holding_id, year_month) 單列；不存在時為無操作。"""
        cursor = self._conn.cursor()
        cursor.execute(_DELETE_ONE, (holding_id, year_month))
        self._conn.commit()

    def replace_all(self, *, records: list[MonthlyRecordModel]) -> None:
        """清空後批次寫入全部紀錄（CSV 匯入用）。"""
        cursor = self._conn.cursor()
        cursor.execute(_DELETE_ALL)
        for record in records:
            cursor.execute(_INSERT, _values(record))
        self._conn.commit()

    @staticmethod
    def _to_dataframe(rows: list[tuple]) -> pd.DataFrame:
        """把查詢 rows 組成固定欄位的 DataFrame（即使空集合也保有欄位）。"""
        return pd.DataFrame(rows, columns=list(_COLUMNS))
