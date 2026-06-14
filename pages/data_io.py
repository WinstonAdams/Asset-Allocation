"""匯出入頁（View / Controller）。

職責：全量匯出三類資料（主檔/月度紀錄/分類目標）為含表頭標準 CSV 供下載；上傳三份 CSV
還原到空庫。委派 DataIoService 整形與驗證、Repository 讀寫。本頁為唯一 catch 點：匯入驗證
失敗（表頭缺漏、唯一鍵重複、孤兒紀錄、目標庫非空等）由 DataIoService 拋領域例外，本頁
catch 後以 st.error 顯示友善訊息，不讓堆疊噴到畫面。

匯出入正確性（含表頭、唯一鍵驗證、還原到空庫等）由下層服務/Repository 的 SC 測試保證；
本頁只做委派與檔案上傳/下載 UI。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.core.exceptions import AssetLabError

logger = logging.getLogger(__name__)


def _container():
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染匯出入頁。"""
    st.title("資料匯出 / 匯入")
    container = _container()

    try:
        _render_export(container=container)
        _render_import(container=container)
    except AssetLabError as error:
        logger.exception("資料匯出入失敗")
        st.error(str(error))


def _render_export(*, container) -> None:
    """全量匯出三類資料為含表頭 CSV，提供下載按鈕。"""
    st.subheader("匯出")
    data_io = container.data_io_service

    holdings_csv = data_io.export_holdings_csv(holdings=container.holding_repo.list_holdings())
    records_csv = data_io.export_records_csv(records=container.record_repo.read_all())
    targets_csv = data_io.export_targets_csv(targets=container.target_repo.read_all())

    st.download_button("下載 holdings.csv", data=holdings_csv, file_name="holdings.csv")
    st.download_button("下載 records.csv", data=records_csv, file_name="records.csv")
    st.download_button("下載 targets.csv", data=targets_csv, file_name="targets.csv")


def _render_import(*, container) -> None:
    """上傳三份 CSV，驗證後還原到空庫（驗證失敗的 catch 在 render 統一處理）。"""
    st.subheader("匯入（還原到空庫）")
    st.warning("匯入僅支援還原到空的資料庫；若庫內已有資料，匯入會被拒絕以免污染。")

    holdings_file = st.file_uploader("holdings.csv", type="csv", key="up_holdings")
    records_file = st.file_uploader("records.csv", type="csv", key="up_records")
    targets_file = st.file_uploader("targets.csv", type="csv", key="up_targets")

    if not st.button("執行匯入"):
        return
    if holdings_file is None or records_file is None or targets_file is None:
        st.error("請同時提供三份 CSV（holdings、records、targets）。")
        return

    record_repo = container.record_repo
    holding_repo = container.holding_repo
    target_repo = container.target_repo

    # 目標庫是否為空屬 I/O 事實，由 Page 查詢後以旗標餵入純整形服務（服務不做 I/O）
    target_db_empty = record_repo.read_all().empty and not holding_repo.list_holdings()

    holdings, records, targets = container.data_io_service.parse_and_validate(
        holdings_csv=holdings_file.getvalue(),
        records_csv=records_file.getvalue(),
        targets_csv=targets_file.getvalue(),
        target_db_empty=target_db_empty,
    )
    holding_repo.replace_all(holdings=holdings)
    record_repo.replace_all(records=records)
    for target in targets:
        target_repo.upsert_target(target=target)
    st.success("匯入完成")


render()
