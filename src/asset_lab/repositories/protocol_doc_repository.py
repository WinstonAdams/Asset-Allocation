"""行為協定文件（docs/PROTOCOL.md）唯讀 I/O。路徑由 bootstrap 注入。"""

# ==== 原生（標準庫） ====
from pathlib import Path

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.exceptions import ProtocolDocError


class ProtocolDocRepository:
    """行為協定文件唯讀 I/O。連線無關，路徑由 bootstrap 以 __file__ 錨定 repo 根注入。"""

    def __init__(self, *, doc_path: Path) -> None:
        """初始化協定文件 Repository。

        Args:
            doc_path: 協定文件的絕對路徑。
        """
        self._doc_path = doc_path

    def read_protocol_markdown(self) -> str:
        """以 UTF-8 讀協定文件全文。

        Raises:
            ProtocolDocError: 讀檔失敗（檔案不存在、路徑非檔案、無讀取權限等任何原因）。
        """
        try:
            return self._doc_path.read_text(encoding="utf-8")
        except OSError as error:
            # 使用者可見訊息不含伺服器絕對路徑（避免洩漏部署目錄結構）；完整路徑與底層
            # OSError 細節經 `from error` 保留在例外鏈，由 Page 層 logger.exception 記入
            # server log 供除錯（比照 data_io_service 的讀檔/解析失敗處理慣例）。
            raise ProtocolDocError(
                "無法讀取行為協定文件，請確認部署包含 docs/PROTOCOL.md。"
            ) from error
