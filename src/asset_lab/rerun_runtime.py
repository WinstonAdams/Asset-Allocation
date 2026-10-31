"""重跑量測的 runtime 黏合：每次最外層執行結束時記一行耗時與資料庫往返次數。

Streamlit 每次互動都會重跑腳本（整頁或 fragment）；本模組只負責量測與記 log，畫面不顯示
任何量測資訊。log 行不含 email 或任何個資。
"""

# ==== 原生（標準庫） ====
import functools
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.constants import RERUN_KIND
from asset_lab.error_boundary import error_boundary
from asset_lab.repositories.query_metrics import QueryMetrics

if TYPE_CHECKING:
    from asset_lab.bootstrap import Container

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)

# 放行後把組裝好的依賴容器存入 session，供各頁以同一容器取用，免每頁重組。
CONTAINER_SESSION_KEY = "container"

# 頁面名稱尚未知道（例如登入守門就被擋下）時的佔位，讓 log 行欄位數固定、好 grep。
_UNKNOWN_PAGE = "-"


class _ScopeState(threading.local):
    """每執行緒的 scope 巢狀深度與本次執行的連線驗證結果。"""

    def __init__(self) -> None:
        """初始化本執行緒的巢狀深度與驗證暫存。"""
        self.depth = 0
        # 本次執行已驗證過的容器；最外層 scope 結束時清掉，下一次執行才會重新驗證。
        self.verified: Container | None = None


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
            _state.verified = None
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


def verified_container() -> "Container":
    """取得本次執行已驗證連線的容器；同一次執行只探測一次。

    第一次呼叫才經 bootstrap 做連線確認（含必要的重連），成功後在入口判定讀取快取是否
    到期；之後同一次執行（含 widget callback 與腳本主體，同一執行緒）直接回傳暫存結果。
    探測失敗時不暫存，例外原樣往上拋，也不做到期判定。

    Returns:
        連線已驗證存活的容器；同時寫入 session_state 供各頁取用。
    """
    container = _state.verified
    if container is None:
        container = bootstrap.get_resilient_container()
        # 到期判定只在每次執行的入口做一次，同一次重跑看到的是同一批資料
        bootstrap.get_read_cache().expire_if_stale()
        _state.verified = container
    st.session_state[CONTAINER_SESSION_KEY] = container
    return container


def rerun_fragment(*, label: str) -> Callable[[F], F]:
    """把函式包成可單獨重跑的 fragment，並補上整頁重跑時 app.py 提供的三件事。

    由外到內：st.fragment → 量測區塊 → 錯誤兜底 → 連線驗證 → 原函式。fragment 單獨重跑時
    不經過 app.py，所以這裡自己計時（整頁重跑時外層已有區塊，不重複記）、自己驗證連線，
    並接住 fragment 內的例外（fragment 內拋出的例外外層接不到）。st.rerun 等控制例外不攔截。

    Args:
        label: fragment 的名稱，作為 log 的 page 欄位與錯誤 log 的位置標籤。

    Returns:
        裝飾器。被裝飾函式的參數須是穩定的識別值，不要傳容器或資料物件，因為 fragment
        單獨重跑時沿用的是上一次整頁重跑傳入的參數，物件可能已過時。
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            # 執行時才透過模組屬性取用，測試才能替換
            metrics = bootstrap.get_query_metrics()
            with rerun_scope(kind=RERUN_KIND.FRAGMENT, metrics=metrics, page=label):
                with error_boundary(context=label):
                    verified_container()
                    return func(*args, **kwargs)

        return st.fragment(wrapper)

    return decorator
