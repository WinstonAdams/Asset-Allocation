"""bootstrap.py 的可測組裝邏輯測試。

bootstrap 的 st.cache_resource 包裝與 st.secrets 讀取屬無法純測的 Streamlit runtime 副作用，
但其中兩段邏輯是純函式、與 runtime 無關，故抽出獨立測試：

1. parse_allowed_emails：把 st.secrets 讀回的允許清單原始值（可能是清單、逗號分隔字串或
   單一字串）正規化成 set，供守門判定（t10 的 evaluate_access）使用。允許 email 屬個資，
   測試一律用虛構值，不出現任何真實 email（遵守敏感資料護欄）。
2. build_container：以 keyword args 把連線注入各 Repository、再把 Repository 注入各 Service，
   組出單一容器。可注入假連線斷言「依賴有被正確接上」，不需 Streamlit runtime。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest
from streamlit.errors import StreamlitSecretNotFoundError

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.data_io_service import DataIoService
from asset_lab.services.monthly_input_service import MonthlyInputService
from asset_lab.services.period_service import PeriodService
from asset_lab.services.return_service import ReturnService


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
    # 所有 Repository 接上同一連線
    assert container.holding_repo._conn is conn
    assert container.record_repo._conn is conn
    assert container.target_repo._conn is conn
    assert container.schema_repo._conn is conn


def test_build_container_wires_services() -> None:
    """容器組出各 Service；月度錄入服務接上主檔與紀錄 Repository（其餘為純運算無依賴）。"""
    conn = _FakeConnection()

    container = bootstrap.build_container(conn=conn)

    assert isinstance(container.return_service, ReturnService)
    assert isinstance(container.allocation_service, AllocationService)
    assert isinstance(container.period_service, PeriodService)
    assert isinstance(container.data_io_service, DataIoService)
    assert isinstance(container.monthly_input_service, MonthlyInputService)
    # 月度錄入服務的 I/O 委派接上容器內的 Repository 實例
    assert container.monthly_input_service._record_repo is container.record_repo
    assert container.monthly_input_service._holding_repo is container.holding_repo
