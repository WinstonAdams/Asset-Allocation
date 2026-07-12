"""行為協定文件唯讀讀取：讀全文成功／讀檔失敗友善拋出（SC-048）。

直接讀真實 `docs/PROTOCOL.md`（已存在磁碟，尚未進版控）驗證讀取成功且內容為目前最新全文；
缺失／不可讀分支以 tmp_path 注入假路徑驗證，不觸碰任何真實檔案系統風險。另以
bootstrap 真實接線（假連線）驗證容器組裝出的 protocol_doc_repo 確實指向 repo 根下的
docs/PROTOCOL.md，端到端鎖定 AD-5 的 `__file__` 錨定路徑解析不因本機/部署差異而失準。
"""

# ==== 原生（標準庫） ====
from pathlib import Path

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.exceptions import ProtocolDocError
from asset_lab.repositories.protocol_doc_repository import ProtocolDocRepository

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_PROTOCOL_DOC_PATH = REPO_ROOT / "docs" / "PROTOCOL.md"


class _FakeConnection:
    """假連線：只佔位供 bootstrap.build_container 組裝，本檔不驗證任何 SQL I/O。"""


class TestReadProtocolMarkdownSucceeds:
    """讀取真實協定文件全文成功，且為磁碟上的最新內容（SC-048 happy）。"""

    @pytest.mark.scenario("SC-048")
    def test_sc048_reads_full_markdown_text_from_real_file(self):
        repo = ProtocolDocRepository(doc_path=REAL_PROTOCOL_DOC_PATH)

        text = repo.read_protocol_markdown()

        # 逐次重讀磁碟原文比對，確保取得的是「文件當前最新內容」而非快取的舊值
        assert text == REAL_PROTOCOL_DOC_PATH.read_text(encoding="utf-8")

    @pytest.mark.scenario("SC-048")
    def test_sc048_content_covers_all_protocol_sections(self):
        # THEN 要求含各節：存在理由、情境分級、機動加碼規則、行為防火牆、事前授權例外、檢核
        repo = ProtocolDocRepository(doc_path=REAL_PROTOCOL_DOC_PATH)

        text = repo.read_protocol_markdown()

        for heading in (
            "本協定存在的理由",
            "情境分級與對應動作",
            "機動加碼規則",
            "行為防火牆",
            "事前授權的例外",
            "檢核",
        ):
            assert heading in text


class TestReadProtocolMarkdownFailsFriendly:
    """檔案缺失／無法讀取時一律拋 ProtocolDocError，交 Page 層轉友善錯誤（SC-048 錯誤）。"""

    @pytest.mark.scenario("SC-048")
    def test_sc048_missing_file_raises_protocol_doc_error(self, tmp_path):
        missing_path = tmp_path / "does-not-exist" / "PROTOCOL.md"
        repo = ProtocolDocRepository(doc_path=missing_path)

        with pytest.raises(ProtocolDocError):
            repo.read_protocol_markdown()

    @pytest.mark.scenario("SC-048")
    def test_sc048_directory_path_raises_protocol_doc_error_not_raw_os_error(self, tmp_path):
        # 路徑指向目錄而非檔案：踩到另一種 OSError 子類（IsADirectoryError），
        # 仍須統一包成 ProtocolDocError，不讓底層例外型別外洩到 Page 層
        directory_path = tmp_path / "a-directory"
        directory_path.mkdir()
        repo = ProtocolDocRepository(doc_path=directory_path)

        with pytest.raises(ProtocolDocError):
            repo.read_protocol_markdown()


class TestBootstrapWiresRealProtocolDocPath:
    """容器組裝出的 protocol_doc_repo 指向 repo 根下的真實 docs/PROTOCOL.md（SC-048 端到端）。

    鎖定 AD-5「以 __file__ 錨定 repo 根」的路徑解析：無論從何處觸發測試執行（pytest 的
    working directory 可能不是 repo 根），組裝出的路徑都必須解析到同一份真實檔案，
    本機與 Streamlit Cloud 部署皆可用，不依賴 CWD。
    """

    @pytest.mark.scenario("SC-048")
    def test_sc048_container_protocol_doc_repo_reads_real_file(self):
        container = bootstrap.build_container(conn=_FakeConnection())

        text = container.protocol_doc_repo.read_protocol_markdown()

        assert text == REAL_PROTOCOL_DOC_PATH.read_text(encoding="utf-8")

    @pytest.mark.scenario("SC-048")
    def test_sc048_module_level_path_resolves_to_repo_root_docs_file(self):
        assert bootstrap._PROTOCOL_DOC_PATH == REAL_PROTOCOL_DOC_PATH
