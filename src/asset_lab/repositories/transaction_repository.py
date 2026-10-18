"""寫入交易邊界：多 statement、單一 commit 的寫入共用同一套失敗處理。

libsql 的寫入錯誤以標準庫 ValueError 拋出，與程式錯誤無法用型別區分；唯一能精準判定
「這是寫入失敗」的位置，就是 try 區塊只含 execute / commit 的交易邊界。因此在此把失敗
轉譯為領域例外 PersistenceError（原始錯誤保留於 `__cause__`），Page 既有的
AssetLabError 捕捉即可顯示友善訊息。本層不記錄錯誤，細節交上層 log。
"""

# ==== 原生（標準庫） ====
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

# ==== 專案內部 ====
from asset_lab.core.exceptions import AssetLabError, PersistenceError

if TYPE_CHECKING:
    from libsql import Connection


@contextmanager
def write_transaction(conn: "Connection") -> Iterator[Any]:
    """開啟單一寫入交易，yield cursor；正常結束 commit，失敗則 rollback。

    - 區塊內或 commit 失敗的 Exception：先 rollback，再轉成 PersistenceError；原例外已是
      領域例外（AssetLabError）時，rollback 後原樣往上拋。
    - rollback 本身失敗：把該錯誤以 note 附在原例外上，仍拋出同樣結果，避免畫面露出堆疊。
    - 非 Exception 的 BaseException（如 KeyboardInterrupt、Streamlit 的 rerun 訊號）：
      rollback 後原樣往上拋，不轉換。

    Args:
        conn: libsql 連線。

    Yields:
        交易內使用的 cursor。

    Raises:
        PersistenceError: 寫入或 commit 失敗（已 rollback）。
    """
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as error:
        _rollback_quietly(conn, error)
        if isinstance(error, AssetLabError):
            raise
        raise PersistenceError() from error
    except BaseException as error:
        _rollback_quietly(conn, error)
        raise


def _rollback_quietly(conn: "Connection", original: BaseException) -> None:
    """rollback；若 rollback 也失敗，把錯誤附註在原例外上而不中斷轉譯流程。"""
    try:
        conn.rollback()
    except Exception as rollback_error:
        original.add_note(f"rollback 失敗：{rollback_error!r}")


class TransactionRepository:
    """跨 Repository 的寫入交易入口（如 CSV 整批匯入）。"""

    def __init__(self, *, conn: "Connection") -> None:
        self._conn = conn

    def transaction(self):
        """開啟寫入交易 context，yield cursor 供各 Repository 的 *_with_context 方法使用。"""
        return write_transaction(self._conn)
