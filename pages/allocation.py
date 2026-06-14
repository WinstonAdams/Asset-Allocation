"""資產配置頁（View / Controller）。

職責：渲染四張配置/趨勢圖——圓餅（選定月資產佔比）、堆疊面積（各分類佔比隨月變化）、
淨值折線（可疊加總資產/總負債）、累積報酬走勢——委派 AllocationService 與 ReturnService
算資料、交 charts 元件畫 Plotly Figure 後以 st.plotly_chart 呈現。本頁為唯一 catch 點。

圖表的業務正確性（僅資產、缺月不補、百分比口徑等）由下層服務的 SC 測試保證；本頁只做
委派與呈現，不算任何業務值。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab import charts
from asset_lab.core.exceptions import AssetLabError

logger = logging.getLogger(__name__)


def _container():
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染資產配置頁。"""
    st.title("資產配置")
    container = _container()
    holding_repo = container.holding_repo
    record_repo = container.record_repo
    allocation_service = container.allocation_service
    return_service = container.return_service

    try:
        holdings = holding_repo.list_holdings()
        latest_ym = record_repo.latest_year_month()
        if latest_ym is None:
            st.write("尚無月度紀錄，請先到「月度錄入」頁輸入資料。")
            return

        _render_pie(
            record_repo=record_repo,
            allocation_service=allocation_service,
            holdings=holdings,
            latest_ym=latest_ym,
        )
        _render_area(
            record_repo=record_repo,
            allocation_service=allocation_service,
            holdings=holdings,
            latest_ym=latest_ym,
        )
        _render_net_worth(
            record_repo=record_repo,
            allocation_service=allocation_service,
            holdings=holdings,
            latest_ym=latest_ym,
        )
        _render_cumulative_twr(
            record_repo=record_repo,
            return_service=return_service,
            holdings=holdings,
            latest_ym=latest_ym,
        )
    except AssetLabError as error:
        logger.exception("資產配置頁渲染失敗")
        st.error(str(error))


def _render_pie(*, record_repo, allocation_service, holdings, latest_ym: str) -> None:
    """選定月份資產配置圓餅（可切項目/分類粒度）。"""
    st.subheader("配置佔比（圓餅）")
    by = st.radio("粒度", options=["category", "holding"], horizontal=True)
    month_records = record_repo.read_month(year_month=latest_ym)
    snapshot = allocation_service.snapshot(
        month_records=month_records, holdings=holdings, by=by
    )
    st.plotly_chart(charts.allocation_pie(snapshot=snapshot), use_container_width=True)


def _render_area(*, record_repo, allocation_service, holdings, latest_ym: str) -> None:
    """各資產分類佔比隨月份變化的堆疊面積圖（區間自開始記錄至最新月）。"""
    st.subheader("配置漂移（堆疊面積）")
    range_df = record_repo.read_range(start_ym="0000-01", end_ym=latest_ym)
    drift_df = allocation_service.drift_series(range_df=range_df, holdings=holdings)
    st.plotly_chart(charts.allocation_area(drift_df=drift_df), use_container_width=True)


def _render_net_worth(*, record_repo, allocation_service, holdings, latest_ym: str) -> None:
    """淨值折線，使用者可勾選疊加總資產/總負債線。"""
    st.subheader("淨值趨勢（折線）")
    show_assets = st.checkbox("疊加總資產線")
    show_liabilities = st.checkbox("疊加總負債線")
    range_df = record_repo.read_range(start_ym="0000-01", end_ym=latest_ym)
    points = allocation_service.net_worth_series(range_df=range_df, holdings=holdings)
    st.plotly_chart(
        charts.net_worth_line(
            points=points, show_assets=show_assets, show_liabilities=show_liabilities
        ),
        use_container_width=True,
    )


def _render_cumulative_twr(*, record_repo, return_service, holdings, latest_ym: str) -> None:
    """整體累積 TWR 走勢（固定單一折線，不提供指標切換）。"""
    st.subheader("報酬率走勢（累積 TWR）")
    range_df = record_repo.read_range(start_ym="0000-01", end_ym=latest_ym)
    points = return_service.cumulative_twr_series(range_df=range_df, holdings=holdings)
    st.plotly_chart(charts.cumulative_twr_line(points=points), use_container_width=True)


render()
