"""資產配置頁（View / Controller）。

職責：渲染四張配置/趨勢圖——圓餅（選定月資產佔比）、堆疊面積（各分類佔比隨月變化）、
淨值折線（可疊加總資產/總負債）、累積報酬走勢——委派 AllocationService 與 ReturnService
算資料、交 charts 元件畫 Plotly Figure 後以 st.plotly_chart 呈現；另以表格呈現當月各分類
相對目標比重的偏離與是否需再平衡（目標比重本身的設定仍在「設定」頁）。本頁為唯一
catch 點。

圖表與偏離計算的業務正確性（僅資產、缺月不補、百分比口徑、偏離門檻等）由下層服務的 SC
測試保證；本頁只做委派與呈現，不算任何業務值。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import pandas as pd
import streamlit as st

# ==== 專案內部 ====
from asset_lab import charts
from asset_lab.bootstrap import Container
from asset_lab.core.constants import DEFAULT_REBALANCE_THRESHOLD, EARLIEST_YEAR_MONTH_SENTINEL
from asset_lab.core.exceptions import AssetLabError
from asset_lab.models.holding import HoldingModel
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.return_service import ReturnService

logger = logging.getLogger(__name__)

# 圓餅圖粒度的中文顯示（內部值需與 AllocationService.snapshot(by=...) 的合約一致）。
_GRANULARITY_LABEL = {"category": "分類", "holding": "項目"}


def _container() -> Container:
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染資產配置頁。"""
    st.title("資產配置")
    container = _container()
    holding_repo = container.holding_repo
    record_repo = container.record_repo
    target_repo = container.target_repo
    allocation_service = container.allocation_service
    return_service = container.return_service

    try:
        holdings = holding_repo.list_holdings()
        latest_ym = record_repo.latest_year_month()
        if latest_ym is None:
            st.write("尚無月度紀錄，請先到「月度錄入」頁輸入資料。")
            return

        # 堆疊面積、淨值折線、累積 TWR 走勢皆用同一份全區間紀錄，讀一次共用避免重複 I/O
        range_df = record_repo.read_range(
            start_ym=EARLIEST_YEAR_MONTH_SENTINEL, end_ym=latest_ym
        )

        _render_pie(
            record_repo=record_repo,
            allocation_service=allocation_service,
            holdings=holdings,
            latest_ym=latest_ym,
        )
        _render_drift(
            holdings=holdings,
            target_repo=target_repo,
            record_repo=record_repo,
            allocation_service=allocation_service,
            latest_ym=latest_ym,
        )
        _render_net_worth(
            allocation_service=allocation_service, holdings=holdings, range_df=range_df
        )
        _render_cumulative_twr(
            return_service=return_service, holdings=holdings, range_df=range_df
        )
        _render_area(
            allocation_service=allocation_service, holdings=holdings, range_df=range_df
        )
    except AssetLabError as error:
        logger.exception("資產配置頁渲染失敗")
        st.error(str(error))


def _render_pie(
    *,
    record_repo: RecordRepository,
    allocation_service: AllocationService,
    holdings: list[HoldingModel],
    latest_ym: str,
) -> None:
    """選定月份資產配置圓餅（可切項目/分類粒度）。"""
    st.subheader("配置佔比（圓餅）")
    by = st.radio(
        "粒度",
        options=["category", "holding"],
        format_func=lambda option: _GRANULARITY_LABEL[option],
        horizontal=True,
    )
    month_records = record_repo.read_month(year_month=latest_ym)
    snapshot = allocation_service.snapshot(
        month_records=month_records, holdings=holdings, by=by
    )
    st.plotly_chart(charts.allocation_pie(snapshot=snapshot), use_container_width=True)


def _render_drift(
    *,
    holdings: list[HoldingModel],
    target_repo: TargetRepository,
    record_repo: RecordRepository,
    allocation_service: AllocationService,
    latest_ym: str,
) -> None:
    """當月各分類相對目標的偏離與是否需再平衡（目標比重本身的設定在「設定」頁）。"""
    st.subheader("目標偏離")
    month_records = record_repo.read_month(year_month=latest_ym)
    snapshot = allocation_service.snapshot(
        month_records=month_records, holdings=holdings, by="category"
    )
    drift_rows = allocation_service.compute_drift(
        snapshot=snapshot,
        targets=target_repo.read_targets(),
        threshold=DEFAULT_REBALANCE_THRESHOLD,
    )
    if not drift_rows:
        st.write("尚未設定任何分類目標比重。")
        return

    st.dataframe(
        [
            {
                "分類": row.category,
                "現況%": round(row.current_weight, 2),
                "目標%": round(row.target_weight, 2),
                "偏離（百分點）": round(row.drift, 2),
                "需再平衡": "是" if row.needs_rebalance else "否",
            }
            for row in drift_rows
        ]
    )


def _render_area(
    *,
    allocation_service: AllocationService,
    holdings: list[HoldingModel],
    range_df: pd.DataFrame,
) -> None:
    """各資產分類佔比隨月份變化的堆疊面積圖（區間自開始記錄至最新月）。"""
    st.subheader("配置漂移（堆疊面積，單位：%）")
    drift_df = allocation_service.drift_series(range_df=range_df, holdings=holdings)
    st.plotly_chart(charts.allocation_area(drift_df=drift_df), use_container_width=True)


def _render_net_worth(
    *,
    allocation_service: AllocationService,
    holdings: list[HoldingModel],
    range_df: pd.DataFrame,
) -> None:
    """淨值折線，使用者可勾選疊加總資產/總負債線。"""
    st.subheader("淨值趨勢（折線，單位：萬元）")
    show_assets = st.checkbox("疊加總資產線")
    show_liabilities = st.checkbox("疊加總負債線")
    points = allocation_service.net_worth_series(range_df=range_df, holdings=holdings)
    st.plotly_chart(
        charts.net_worth_line(
            points=points, show_assets=show_assets, show_liabilities=show_liabilities
        ),
        use_container_width=True,
    )


def _render_cumulative_twr(
    *,
    return_service: ReturnService,
    holdings: list[HoldingModel],
    range_df: pd.DataFrame,
) -> None:
    """整體累積 TWR 走勢（固定單一折線，不提供指標切換）。"""
    st.subheader("報酬率走勢（累積 TWR，單位：%）")
    points = return_service.cumulative_twr_series(range_df=range_df, holdings=holdings)
    st.plotly_chart(charts.cumulative_twr_line(points=points), use_container_width=True)


render()
