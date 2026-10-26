"""重跑量測的 runtime 黏合：每次最外層執行結束時記一行耗時與資料庫往返次數。

Streamlit 每次互動都會重跑腳本（整頁或 fragment）；本模組只負責量測與記 log，畫面不顯示
任何量測資訊。log 行不含 email 或任何個資。
"""

# ==== 原生（標準庫） ====
import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.repositories.query_metrics import QueryMetrics

logger = logging.getLogger(__name__)

# 頁面名稱尚未知道（例如登入守門就被擋下）時的佔位，讓 log 行欄位數固定、好 grep。
_UNKNOWN_PAGE = "-"


class _ScopeState(threading.local):
    """每執行緒的 scope 巢狀深度。"""

    def __init__(self) -> None:
        self.depth = 0


_state = _ScopeState()


@dataclass
class RerunScope:
    """一次執行的量測區塊資訊；page 可在區塊內補上（例如 navigation 解析後才知道）。"""

    kind: str
    page: str | None
    is_outermost: bool


@contextmanager
def rerun_scope(
    *, kind: str, metrics: QueryMetrics, page: str | None = None
) -> Iterator[RerunScope]:
    """可巢狀的計時區塊；只有最外層離開時才讀取並歸零計數、記一行 INFO。

    在離開時才歸零（而非進入時），所以 widget callback 在腳本主體之前產生的往返也會
    算進同一行。不論正常結束或被例外（含 st.stop／st.rerun 的控制例外）中斷都會記錄，
    且不攔截任何例外。

    Args:
        kind: 重跑類型（RERUN_KIND.FULL 或 RERUN_KIND.FRAGMENT）。
        metrics: 本次執行所用的量測累計器。
        page: 頁面或 fragment 名稱；未知時可省略，之後在區塊內指定。

    Yields:
        RerunScope，可在區塊內更新 page。
    """
    scope = RerunScope(kind=kind, page=page, is_outermost=_state.depth == 0)
    _state.depth += 1
    started = time.perf_counter()
    interrupted = True
    try:
        yield scope
        interrupted = False
    finally:
        _state.depth -= 1
        if scope.is_outermost:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            snapshot = metrics.take()
            logger.info(
                "重跑量測 kind=%s page=%s elapsed_ms=%d db_roundtrips=%d cache_hits=%d "
                "reconnected=%s interrupted=%s",
                scope.kind,
                scope.page or _UNKNOWN_PAGE,
                elapsed_ms,
                snapshot.db_roundtrips,
                snapshot.cache_hits,
                str(snapshot.reconnected).lower(),
                str(interrupted).lower(),
            )
