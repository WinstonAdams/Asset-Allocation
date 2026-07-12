"""bootstrap.py 的可測組裝邏輯測試。

bootstrap 的 st.cache_resource 包裝與 st.secrets 讀取屬無法純測的 Streamlit runtime 副作用，
但其中幾段邏輯是純函式、與 runtime 無關，故抽出獨立測試：

1. parse_allowed_emails：把 st.secrets 讀回的允許清單原始值（可能是清單、逗號分隔字串或
   單一字串）正規化成 set，供守門判定（t10 的 evaluate_access）使用。允許 email 屬個資，
   測試一律用虛構值，不出現任何真實 email（遵守敏感資料護欄）。
2. build_container：以 keyword args 把連線注入各 Repository、再把 Repository 注入各 Service，
   組出單一容器。可注入假連線斷言「依賴有被正確接上」，不需 Streamlit runtime。
3. _with_reconnect_on_stale_stream：Turso 遠端連線的 Hrana stream 閒置隔夜會被伺服器端
   關閉，快取住的連線與容器不會自動感知，下次操作即拋「stream not found」類例外整頁崩潰
   （t16 驗收回饋）。此函式把「取容器→驗證存活→失效則清快取重連重試一次」收斂成可注入
   假容器/假快取清除動作的純函式，故以假物件模擬連線失效與重連成功，不需真連 Turso。

另補一段版控範本 secrets.toml.example 的結構回歸測試：TOML 語法中，區塊標頭
（`[section]`）之後、下一個標頭之前的所有 key 都歸屬該區塊，`allowed_emails` 若被放在
`[turso]` 與 `[auth]` 之間會被誤歸入 `turso.allowed_emails`，導致 allowed_emails() 讀
不到頂層值而 fail-closed 擋下所有人（含合法使用者）。此測試鎖定範本解析後的結構。
"""

# ==== 原生（標準庫） ====
import ast
import tomllib
from pathlib import Path
from unittest.mock import Mock

# ==== 第三方套件 ====
import pytest
from streamlit.errors import StreamlitSecretNotFoundError

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.protocol_threshold_repository import ProtocolThresholdRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.data_io_service import DataIoService
from asset_lab.services.monthly_input_service import MonthlyInputService
from asset_lab.services.period_service import PeriodService
from asset_lab.services.protocol_service import ProtocolService
from asset_lab.services.return_service import ReturnService

APP_DIR = Path(__file__).resolve().parent.parent


class _FakeConnection:
    """假連線：只佔位以驗證 Repository 是否接上同一連線，不執行任何 I/O。"""


@pytest.mark.scenario("SC-033")
def test_parse_allowed_emails_from_list_normalizes_and_dedupes() -> None:
    """清單型允許值去前後空白、轉小寫並去重，產出供守門比對的 set。"""
    raw = ["Owner@Example.com", " owner@example.com ", "alt@example.com"]

    result = bootstrap.parse_allowed_emails(raw)

    assert result == {"owner@example.com", "alt@example.com"}


@pytest.mark.scenario("SC-033")
def test_parse_allowed_emails_from_comma_separated_string() -> None:
    """逗號分隔字串拆成多個 email 並各自正規化（secrets 常以單行字串設定）。"""
    raw = "Owner@Example.com, alt@example.com"

    result = bootstrap.parse_allowed_emails(raw)

    assert result == {"owner@example.com", "alt@example.com"}


@pytest.mark.scenario("SC-033")
def test_parse_allowed_emails_from_single_string() -> None:
    """單一 email 字串（無逗號）正規化成單元素 set。"""
    result = bootstrap.parse_allowed_emails("Owner@Example.com")

    assert result == {"owner@example.com"}


@pytest.mark.scenario("SC-034")
def test_parse_allowed_emails_empty_yields_empty_set() -> None:
    """允許清單未設定（None / 空字串 / 空清單）時回空 set，守門將不放行任何人。"""
    assert bootstrap.parse_allowed_emails(None) == set()
    assert bootstrap.parse_allowed_emails("") == set()
    assert bootstrap.parse_allowed_emails("   ") == set()
    assert bootstrap.parse_allowed_emails([]) == set()


@pytest.mark.scenario("SC-034")
def test_parse_allowed_emails_skips_blank_entries() -> None:
    """逗號分隔中夾帶空白片段（如尾逗號）不應產生空字串成員。"""
    result = bootstrap.parse_allowed_emails("owner@example.com, , ")

    assert result == {"owner@example.com"}


@pytest.mark.scenario("SC-034")
def test_allowed_emails_returns_empty_when_no_secrets_file(monkeypatch) -> None:
    """完全沒有 secrets 檔時 allowed_emails 回空 set（fail-closed），不讓守門崩潰。"""

    class _NoSecrets:
        def get(self, key):
            raise StreamlitSecretNotFoundError("No secrets found")

    monkeypatch.setattr(bootstrap.st, "secrets", _NoSecrets())

    assert bootstrap.allowed_emails() == set()


@pytest.mark.scenario("SC-033")
def test_allowed_emails_reads_and_normalizes_from_secrets(monkeypatch) -> None:
    """有設定時 allowed_emails 從 secrets 取值並正規化（虛構值，不寫死真實 email）。"""

    class _Secrets:
        def get(self, key):
            return ["Owner@Example.com"] if key == "allowed_emails" else None

    monkeypatch.setattr(bootstrap.st, "secrets", _Secrets())

    assert bootstrap.allowed_emails() == {"owner@example.com"}


def test_build_container_wires_repositories_to_connection() -> None:
    """容器以注入的同一連線建立各 Repository，並由 DB schema 建表入口備妥。"""
    conn = _FakeConnection()

    container = bootstrap.build_container(conn=conn)

    assert isinstance(container.holding_repo, HoldingRepository)
    assert isinstance(container.record_repo, RecordRepository)
    assert isinstance(container.target_repo, TargetRepository)
    assert isinstance(container.schema_repo, SchemaRepository)
    assert isinstance(container.protocol_threshold_repo, ProtocolThresholdRepository)
    # 所有 Repository 接上同一連線
    assert container.holding_repo._conn is conn
    assert container.record_repo._conn is conn
    assert container.target_repo._conn is conn
    assert container.schema_repo._conn is conn
    assert container.protocol_threshold_repo._conn is conn


def test_build_container_wires_services() -> None:
    """容器組出各 Service；月度錄入服務接上主檔與紀錄 Repository（其餘為純運算無依賴）。"""
    conn = _FakeConnection()

    container = bootstrap.build_container(conn=conn)

    assert isinstance(container.return_service, ReturnService)
    assert isinstance(container.allocation_service, AllocationService)
    assert isinstance(container.period_service, PeriodService)
    assert isinstance(container.data_io_service, DataIoService)
    assert isinstance(container.monthly_input_service, MonthlyInputService)
    assert isinstance(container.protocol_service, ProtocolService)
    # 月度錄入服務的 I/O 委派接上容器內的 Repository 實例
    assert container.monthly_input_service._record_repo is container.record_repo
    assert container.monthly_input_service._holding_repo is container.holding_repo


class _FakeSchemaRepo:
    """假 schema repo：ensure_schema 依建構時指定成功或拋指定例外，模擬連線存活探測。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.call_count = 0

    def ensure_schema(self) -> None:
        self.call_count += 1
        if self._error is not None:
            raise self._error


class _FakeResilientContainer:
    """假容器：_with_reconnect_on_stale_stream 只用得到 schema_repo 這個欄位。"""

    def __init__(self, schema_repo: _FakeSchemaRepo) -> None:
        self.schema_repo = schema_repo


def _make_get_container(*containers: _FakeResilientContainer):
    """依序回傳指定的假容器，並記錄實際被呼叫次數，供斷言重試次數上限。"""
    queue = list(containers)

    def _get_container() -> _FakeResilientContainer:
        _get_container.call_count += 1
        return queue.pop(0)

    _get_container.call_count = 0
    return _get_container


@pytest.mark.scenario("SC-042")
def test_with_reconnect_returns_container_when_connection_alive() -> None:
    """連線存活（ensure_schema 成功）時直接回傳容器，不清任何快取、不重取。"""
    container = _FakeResilientContainer(_FakeSchemaRepo())
    get_container = _make_get_container(container)
    clear_connection_cache = Mock()
    clear_container_cache = Mock()

    result = bootstrap._with_reconnect_on_stale_stream(
        get_container=get_container,
        clear_connection_cache=clear_connection_cache,
        clear_container_cache=clear_container_cache,
    )

    assert result is container
    assert get_container.call_count == 1
    clear_connection_cache.assert_not_called()
    clear_container_cache.assert_not_called()


@pytest.mark.scenario("SC-042")
def test_with_reconnect_recovers_from_stale_stream_error() -> None:
    """首次查詢拋 stream-not-found 類失效時，清兩層快取重連後重試一次即成功。"""
    stale_error = ValueError(
        'Hrana: `api error: `status=404 Not Found, '
        'body={"error":"stream not found: abc123"}``'
    )
    dead_container = _FakeResilientContainer(_FakeSchemaRepo(error=stale_error))
    revived_container = _FakeResilientContainer(_FakeSchemaRepo())
    get_container = _make_get_container(dead_container, revived_container)
    clear_connection_cache = Mock()
    clear_container_cache = Mock()

    result = bootstrap._with_reconnect_on_stale_stream(
        get_container=get_container,
        clear_connection_cache=clear_connection_cache,
        clear_container_cache=clear_container_cache,
    )

    assert result is revived_container
    assert get_container.call_count == 2
    clear_connection_cache.assert_called_once()
    clear_container_cache.assert_called_once()


@pytest.mark.scenario("SC-042")
def test_with_reconnect_reraises_non_stale_business_error() -> None:
    """非連線失效的一般業務例外（如唯一性約束違反）原樣往上拋，不誤判為可重連。"""
    business_error = ValueError("UNIQUE constraint failed: holdings.name")
    container = _FakeResilientContainer(_FakeSchemaRepo(error=business_error))
    get_container = _make_get_container(container)
    clear_connection_cache = Mock()
    clear_container_cache = Mock()

    with pytest.raises(ValueError, match="UNIQUE constraint failed"):
        bootstrap._with_reconnect_on_stale_stream(
            get_container=get_container,
            clear_connection_cache=clear_connection_cache,
            clear_container_cache=clear_container_cache,
        )

    assert get_container.call_count == 1
    clear_connection_cache.assert_not_called()
    clear_container_cache.assert_not_called()


@pytest.mark.scenario("SC-042")
def test_with_reconnect_gives_up_after_second_consecutive_failure() -> None:
    """重連重試一次後仍失效，例外原樣浮出，不無限重連。"""
    stale_error = ValueError('stream not found: abc123')
    first_container = _FakeResilientContainer(_FakeSchemaRepo(error=stale_error))
    second_container = _FakeResilientContainer(_FakeSchemaRepo(error=stale_error))
    get_container = _make_get_container(first_container, second_container)
    clear_connection_cache = Mock()
    clear_container_cache = Mock()

    with pytest.raises(ValueError, match="stream not found"):
        bootstrap._with_reconnect_on_stale_stream(
            get_container=get_container,
            clear_connection_cache=clear_connection_cache,
            clear_container_cache=clear_container_cache,
        )

    assert get_container.call_count == 2
    clear_connection_cache.assert_called_once()
    clear_container_cache.assert_called_once()


def test_is_stale_stream_error_matches_stream_not_found_message() -> None:
    """訊息含 stream not found（含大小寫混合）判定為可重連的連線失效。"""
    exc = ValueError('Hrana: `api error: `status=404, body={"error":"Stream Not Found: x"}``')

    assert bootstrap._is_stale_stream_error(exc) is True


def test_is_stale_stream_error_rejects_unrelated_business_error() -> None:
    """一般業務例外訊息（無 stream not found 字樣）判定為不可重連，避免誤吞。"""
    exc = ValueError("UNIQUE constraint failed: holdings.name")

    assert bootstrap._is_stale_stream_error(exc) is False


def test_secrets_template_keeps_allowed_emails_at_top_level() -> None:
    """secrets.toml.example 的 allowed_emails 須為頂層 key，不得落入任何 [section]。

    回歸防呆：allowed_emails 一旦被放在兩個 [section] 標頭之間，TOML 會把它歸入前一個
    區塊（例如 turso.allowed_emails），allowed_emails() 讀的頂層值即變 None，
    守門因而 fail-closed 擋下所有人（含合法使用者）。
    """
    template_path = APP_DIR / ".streamlit" / "secrets.toml.example"

    with template_path.open("rb") as f:
        parsed = tomllib.load(f)

    assert "allowed_emails" in parsed
    assert "allowed_emails" not in parsed.get("turso", {})
    assert "allowed_emails" not in parsed.get("auth", {})


def _arrow_memory_pool_setdefault_call(node: ast.stmt) -> ast.Call | None:
    """若此頂層敘述是 `os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", ...)` 則回傳該呼叫。"""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return None
    call = node.value
    func = call.func
    is_environ_setdefault = (
        isinstance(func, ast.Attribute)
        and func.attr == "setdefault"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
    )
    if not is_environ_setdefault:
        return None
    targets_arrow_key = any(
        isinstance(arg, ast.Constant) and arg.value == "ARROW_DEFAULT_MEMORY_POOL"
        for arg in call.args
    )
    return call if targets_arrow_key else None


def _is_streamlit_import(node: ast.stmt) -> bool:
    return isinstance(node, ast.Import) and any(alias.name == "streamlit" for alias in node.names)


def test_app_disables_pyarrow_mimalloc_before_importing_streamlit() -> None:
    """app.py 須在 import streamlit 之前，把 ARROW_DEFAULT_MEMORY_POOL 設為 system。

    回歸防呆：pyarrow 25 內建的 mimalloc 配置器在 macOS arm64 有 thread-init segfault，
    Streamlit 顯示 DataFrame（st.dataframe / st.data_editor）觸發 pandas→Arrow 轉換時，
    使用者本機操作（編輯月度錄入、切頁）曾實測整個 Python 進程 EXC_BAD_ACCESS 崩潰。
    設 ARROW_DEFAULT_MEMORY_POOL=system 停用 mimalloc、改用系統 malloc 已驗證可規避，
    但 pyarrow 只在自身被 import 的當下讀取此環境變數一次——而 Streamlit 一 import 就
    連帶 import pyarrow，因此這行必須在 `import streamlit` 之前執行才有效、且值須為
    "system"。segfault 本身難以在單元測試重現，故改以原始碼層級（AST）鎖定兩者的先後
    順序與設定值，避免日後有人不知情把 import 重新排序或誤刪這行、誤改值。
    """
    app_path = APP_DIR / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"), filename=str(app_path))

    setdefault_calls = [
        (node.lineno, call)
        for node in tree.body
        if (call := _arrow_memory_pool_setdefault_call(node)) is not None
    ]
    streamlit_import_lines = [node.lineno for node in tree.body if _is_streamlit_import(node)]

    assert setdefault_calls, "app.py 應設定 os.environ.setdefault('ARROW_DEFAULT_MEMORY_POOL', ...)"
    assert streamlit_import_lines, "app.py 應 import streamlit"

    setdefault_line, call = setdefault_calls[0]
    assert setdefault_line < streamlit_import_lines[0], (
        "ARROW_DEFAULT_MEMORY_POOL 必須在 import streamlit 之前設定，"
        "否則 pyarrow 已在 streamlit import 當下讀走舊值，設定不會生效"
    )
    assert call.args[1].value == "system", (
        "ARROW_DEFAULT_MEMORY_POOL 須設為 'system' 才會停用 mimalloc"
    )
