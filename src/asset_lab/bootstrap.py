"""依賴組裝與 Streamlit runtime 接點。

把 Repository 與 Service 以 keyword args 組成單一容器，並在 Streamlit 常駐進程中以
@st.cache_resource 確保連線與容器只建一次（避免每次 rerun 重建連線、重連 Turso）。

機密一律來自 st.secrets（本機 .streamlit/secrets.toml、雲端 Secrets UI），不寫死任何
Turso 憑證、OAuth 設定或允許登入 email；本模組只負責「從 secrets 取出後注入」，下層
Repository/Service 不直接讀 st.secrets。

純組裝邏輯（build_container）與允許清單解析（parse_allowed_emails）與 runtime 無關，
另抽為可獨立測試的純函式；get_connection / get_container / allowed_emails 為其薄包裝，
負責 st.cache_resource 與 st.secrets 讀取。

`@st.cache_resource` 只保證「進程存活期間不重建」，不代表遠端連線本身恆久有效——Turso
的 Hrana stream 閒置過久會被伺服器端關閉，快取住的連線物件不會自動感知，下次操作即拋
「stream not found」類例外。`get_resilient_container()`（app.py 實際呼叫的入口）在
`get_container()` 之上加一層存活驗證與自動重連重試，見該函式 docstring。
"""

# ==== 原生（標準庫） ====
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

# ==== 第三方套件 ====
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

# ==== 專案內部 ====
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.data_io_service import DataIoService
from asset_lab.services.monthly_input_service import MonthlyInputService
from asset_lab.services.period_service import PeriodService
from asset_lab.services.return_service import ReturnService

if TYPE_CHECKING:
    from libsql import Connection

# st.secrets 內 Turso 連線設定的區段與鍵；值為機密，只存在於 secrets，不寫死於此。
_SECRET_TURSO_SECTION = "turso"
_SECRET_TURSO_URL = "database_url"
_SECRET_TURSO_TOKEN = "auth_token"

# st.secrets 內允許登入 email 的鍵；email 屬個資，只存在於 secrets。
_SECRET_ALLOWED_EMAILS = "allowed_emails"


@dataclass(frozen=True)
class Container:
    """已組裝的依賴容器，供 Page 取用各 Repository 與 Service。

    所有依賴在此一次組好（連線注入 Repository、Repository 注入需要 I/O 的 Service），
    Page 不自行 new 任何 Repository/Service，只從容器取用。
    """

    holding_repo: HoldingRepository
    record_repo: RecordRepository
    target_repo: TargetRepository
    schema_repo: SchemaRepository
    return_service: ReturnService
    allocation_service: AllocationService
    period_service: PeriodService
    data_io_service: DataIoService
    monthly_input_service: MonthlyInputService


def parse_allowed_emails(raw: object) -> set[str]:
    """把 st.secrets 讀回的允許 email 原始值正規化成比對用 set。

    secrets 可能以多種形態設定允許清單：TOML 陣列（清單）、逗號分隔的單行字串、或單一
    email 字串。一律拆解、去前後空白並轉小寫後組成 set（與守門判定的 email 正規化一致），
    空白片段（如尾逗號造成）略過。未設定（None / 空）時回空 set——守門將不放行任何人，
    確保「漏設允許清單」會傾向擋下而非放行。

    Args:
        raw: st.secrets 讀回的允許清單原始值（清單、逗號分隔字串、單一字串或 None）。

    Returns:
        正規化後的允許 email set；未設定時為空 set。
    """
    if raw is None:
        return set()

    if isinstance(raw, str):
        candidates: Iterable[str] = raw.split(",")
    elif isinstance(raw, Iterable):
        candidates = [str(item) for item in raw]
    else:
        candidates = [str(raw)]

    return {email.strip().lower() for email in candidates if email.strip()}


def build_container(*, conn: "Connection") -> Container:
    """以注入的連線組裝全部 Repository 與 Service（純組裝，無 I/O、無 st.*）。

    連線以 keyword args 注入各 Repository；需要 I/O 的 Service（月度錄入）再以 keyword
    args 接上對應 Repository；純運算 Service（報酬/配置/區間/CSV 整形）無依賴直接建立。

    Args:
        conn: libsql 連線；正式由 get_connection 提供，測試可注入假連線驗證接線。

    Returns:
        組裝完成的 Container。
    """
    holding_repo = HoldingRepository(conn=conn)
    record_repo = RecordRepository(conn=conn)
    target_repo = TargetRepository(conn=conn)
    schema_repo = SchemaRepository(conn=conn)

    return Container(
        holding_repo=holding_repo,
        record_repo=record_repo,
        target_repo=target_repo,
        schema_repo=schema_repo,
        return_service=ReturnService(),
        allocation_service=AllocationService(),
        period_service=PeriodService(),
        data_io_service=DataIoService(),
        monthly_input_service=MonthlyInputService(
            holding_repo=holding_repo, record_repo=record_repo
        ),
    )


@st.cache_resource
def get_connection() -> "Connection":
    """建立並快取 Turso 連線（每進程一次，跨 rerun 不重建）。

    連線憑證（URL、auth token）一律從 st.secrets 取得，不寫死於程式。

    Returns:
        已建立的 libsql 連線。
    """
    # 延遲匯入：libsql 僅在實際連線時需要，且方便無 runtime 的單元測試免裝此套件。
    import libsql

    turso = st.secrets[_SECRET_TURSO_SECTION]
    return libsql.connect(
        database=turso[_SECRET_TURSO_URL],
        auth_token=turso[_SECRET_TURSO_TOKEN],
    )


@st.cache_resource
def get_container() -> Container:
    """組裝並快取依賴容器，且在首次組裝時確保資料表存在。

    以快取的連線組出容器，並呼叫建表入口（if not exists，重複安全），使 app 首次啟動
    即備妥三張表。跨 rerun 復用同一容器，避免重複建連線與建表。

    Returns:
        已組裝且 schema 就緒的 Container。
    """
    container = build_container(conn=get_connection())
    container.schema_repo.ensure_schema()
    return container


# Turso Hrana stream 閒置逾時失效時，libsql 拋出的例外訊息固定含此關鍵字（依實測樣態
# 為 ValueError，但 libsql 的 Python binding 不保證固定例外型別，故以訊息內容判斷而非
# 型別判斷更穩定）。SQL 語法錯、UNIQUE 約束違反等業務例外訊息不含此關鍵字，不會誤判。
_STALE_STREAM_MARKER = "stream not found"


def _is_stale_stream_error(exc: Exception) -> bool:
    """判斷例外是否為『連線 stream 已失效但可重連』的樣態，而非一般業務例外。

    Args:
        exc: repo/service 呼叫時往上拋出的例外。

    Returns:
        True 表示屬可重連的連線失效；False 表示應視為一般例外原樣往上拋（不可誤判
        並吞掉重試，否則會把 SQL 語法錯、約束違反等正常業務例外也當成連線問題重試）。
    """
    return _STALE_STREAM_MARKER in str(exc).lower()


def _with_reconnect_on_stale_stream(
    *,
    get_container: Callable[[], Container],
    clear_connection_cache: Callable[[], None],
    clear_container_cache: Callable[[], None],
) -> Container:
    """取容器並以 `ensure_schema()` 驗證連線存活；偵測到失效則清快取重連重試一次。

    `ensure_schema()` 是 idempotent 的 `CREATE TABLE IF NOT EXISTS`，順便當作連線存活
    探測——若底層 Hrana stream 已失效，會在這裡先踩到，而非等使用者頁面查詢時才崩潰
    （假設：同一條連線若 stream 已死，其上任何操作都會以同一樣態失敗，故此探測結果
    可代表該連線本次 rerun 對所有 Repository 呼叫皆有效）。

    偵測到可重連的失效樣態時，依序清掉連線與容器兩層快取——`get_container()` 組裝的
    各 Repository 在建構時就綁定了舊連線物件，只清連線快取不足以讓既有 Repository
    改用新連線，必須連容器一起重建——重取一次並再驗證一次。非可重連例外（SQL 語法
    錯、約束違反等業務例外）原樣往上拋，不誤判為可重連而吞掉。最多重試一次：第二次
    仍失敗就讓例外原樣浮出，不無限重連。

    Args:
        get_container: 取得（可能快取的）容器；重連後會再呼叫一次取得新容器。
        clear_connection_cache: 清除連線快取（`get_connection.clear`）。
        clear_container_cache: 清除容器快取（`get_container.clear`）。

    Returns:
        連線已驗證存活（或重連成功）的容器。
    """
    container = get_container()
    try:
        container.schema_repo.ensure_schema()
    except Exception as exc:
        if not _is_stale_stream_error(exc):
            raise
        clear_connection_cache()
        clear_container_cache()
        container = get_container()
        container.schema_repo.ensure_schema()
    return container


def get_resilient_container() -> Container:
    """app.py 實際取用容器的入口：確保連線存活，失效時自動清快取重連並重試一次。

    每次 rerun 都會呼叫（見 `_with_reconnect_on_stale_stream`），取代直接呼叫
    `get_container()`——後者本身仍是單純的 cached 組裝，不含存活驗證與重連。

    Returns:
        連線已驗證存活的容器。
    """
    return _with_reconnect_on_stale_stream(
        get_container=get_container,
        clear_connection_cache=get_connection.clear,
        clear_container_cache=get_container.clear,
    )


def allowed_emails() -> set[str]:
    """從 st.secrets 讀允許登入 email 清單並正規化（個資不寫死）。

    完全沒有任何 secrets 檔（首次啟動、尚未設定）時 st.secrets 會拋 not-found；視為
    「未設定允許清單」回空 set——守門因而不放行任何人並導向登入畫面，是 fail-closed 的
    安全預設，而非以原始堆疊讓整頁崩潰。

    Returns:
        正規化後的允許 email set；secrets 未設定時為空 set。
    """
    try:
        raw = st.secrets.get(_SECRET_ALLOWED_EMAILS)
    except StreamlitSecretNotFoundError:
        return set()
    return parse_allowed_emails(raw)
