"""行為協定頁（View）。

職責：以 markdown 唯讀渲染 `docs/PROTOCOL.md` 全文，供使用者在市場大跌時查閱預先設定的
行為協定；不提供任何編輯或儲存入口。文件讀取委派 ProtocolDocRepository；讀檔失敗（缺失、
無法讀取等）在本頁轉為友善錯誤提示，不外洩技術堆疊。本頁為唯一 catch 點。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.bootstrap import Container
from asset_lab.core.exceptions import AssetLabError

logger = logging.getLogger(__name__)


def _container() -> Container:
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染行為協定頁：唯讀呈現協定文件全文。"""
    st.title("行為協定")
    container = _container()

    try:
        markdown_text = container.protocol_doc_repo.read_protocol_markdown()
        st.markdown(markdown_text)
    except AssetLabError as error:
        logger.exception("行為協定頁讀取協定文件失敗")
        st.error(str(error))


render()
