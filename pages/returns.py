"""報酬率頁（View / Controller）。

職責：讓使用者選報酬維度（整體/分類/單一標的）與區間（自開始記錄/今年以來/近一年/自訂），
委派 PeriodService 解析區間、ReturnService 算三口徑報酬率，逐維度呈現 TWR、MWR、簡單總報酬
率與賺賠金額。MWR 不收斂（資料層回 None）時降級為「無法計算」，不影響並列的 TWR 與賺賠。
本頁為唯一 catch 點。

報酬率口徑正確性由下層服務的 SC 測試保證；本頁只做委派、區間選擇與呈現。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.core.constants import EARLIEST_YEAR_MONTH_SENTINEL, PERIOD_MODE
from asset_lab.core.exceptions import AssetLabError

logger = logging.getLogger(__name__)

# MWR 無法收斂時的降級顯示文字（與資料層的 not_converged 狀態對應）。
_MWR_UNAVAILABLE = "無法計算"


def _container():
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染報酬率頁。"""
    st.title("報酬率")
    container = _container()
    record_repo = container.record_repo
    holding_repo = container.holding_repo
    return_service = container.return_service
    period_service = container.period_service

    try:
        latest_ym = record_repo.latest_year_month()
        if latest_ym is None:
            st.write("尚無月度紀錄，請先到「月度錄入」頁輸入資料。")
            return

        dimension = st.radio(
            "維度", options=["overall", "category", "holding"], horizontal=True
        )
        start_ym, end_ym = _resolve_period(
            period_service=period_service, record_repo=record_repo, latest_ym=latest_ym
        )

        range_df = record_repo.read_range(start_ym=start_ym, end_ym=end_ym)
        holdings = holding_repo.list_holdings()
        results = return_service.compute_returns(
            range_df=range_df,
            holdings=holdings,
            dimension=dimension,
            start_ym=start_ym,
            end_ym=end_ym,
        )
        _render_results(results)
    except AssetLabError as error:
        logger.exception("報酬率頁渲染失敗")
        st.error(str(error))


def _resolve_period(*, period_service, record_repo, latest_ym: str) -> tuple[str, str]:
    """讀區間模式與自訂起訖，委派 PeriodService 解析為 (起月, 訖月)。"""
    mode = st.selectbox("區間", options=list(PERIOD_MODE.ALL))
    custom_start = custom_end = None
    if mode == PERIOD_MODE.CUSTOM:
        custom_start = st.text_input("自訂起月（YYYY-MM）")
        custom_end = st.text_input("自訂訖月（YYYY-MM）")

    range_df = record_repo.read_range(start_ym=EARLIEST_YEAR_MONTH_SENTINEL, end_ym=latest_ym)
    earliest_ym = (
        str(range_df["year_month"].min()) if not range_df.empty else latest_ym
    )
    return period_service.resolve_period(
        mode=mode,
        latest_ym=latest_ym,
        earliest_ym=earliest_ym,
        custom_start=custom_start or None,
        custom_end=custom_end or None,
    )


def _render_results(results) -> None:
    """逐維度呈現報酬率；MWR 不收斂時降級為「無法計算」。"""
    if not results:
        st.write("此區間無可計算的資產報酬。")
        return

    for result in results:
        label = result.dimension_key or "整體"
        st.markdown(f"### {label}")
        twr = _format_percent(result.twr)
        mwr = _MWR_UNAVAILABLE if result.mwr is None else _format_percent(result.mwr)
        simple = _format_percent(result.simple_return)
        suffix = "（年化）" if result.annualized else "（區間累積）"

        columns = st.columns(4)
        columns[0].metric(f"TWR{suffix}", twr)
        columns[1].metric(f"MWR{suffix}", mwr)
        columns[2].metric("簡單總報酬率", simple)
        columns[3].metric(
            "賺賠金額", "—" if result.pnl_amount is None else f"{result.pnl_amount:,.0f}"
        )


def _format_percent(value: float | None) -> str:
    """把報酬率小數格式化為百分比字串；None 顯示破折號。"""
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


render()
