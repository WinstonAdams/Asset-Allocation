"""總覽頁（View / Controller）——登入後預設落地頁。

職責：取全歷史月度紀錄 → 委派 `ReturnService.cumulative_twr_series` 取累積 TWR 序列
→ 委派 `ProtocolService` 取有效門檻並判定目前協定等級（`assess`）→ 委派
`overview_presentation.resolve_presentation` 轉換為呈現資料 → 渲染等級燈號/回撤帶、
必做/禁止摘要與關鍵指標（累積 TWR、淨值、目前自歷史高點回撤%）。尚無任何月度紀錄
時直接以「無資料」姿態呈現，不觸發任何區間查詢（避免以 null 訖月查詢）。本頁為唯一
catch 點。

等級判定與回撤計算的業務正確性由 ProtocolService 的 SC 測試保證；level_code 查表與
狀態轉呈現資料的邏輯由 overview_presentation 的 SC 測試保證；本頁只做委派、資料組裝
與渲染，不算任何業務值（AD-6：只消費既有 ReturnService/AllocationService 輸出）。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab import overview_presentation
from asset_lab.bootstrap import Container
from asset_lab.core.constants import (
    EARLIEST_YEAR_MONTH_SENTINEL,
    PROTOCOL_LEVEL_CODE,
    PROTOCOL_MIN_DATA_MONTHS,
)
from asset_lab.core.exceptions import AssetLabError
from asset_lab.models.results import ProtocolStatus

logger = logging.getLogger(__name__)

# 燈號 emoji：對映等級代碼，供畫面上的等級指示（平時 → 深熊漸次升高警覺）。
_SIGNAL_EMOJI = {
    PROTOCOL_LEVEL_CODE.L0: "🟢",
    PROTOCOL_LEVEL_CODE.L1: "🟡",
    PROTOCOL_LEVEL_CODE.L2: "🟠",
    PROTOCOL_LEVEL_CODE.L3: "🔴",
}

# 尚無任何月度紀錄時的判定結果：不觸發區間查詢，直接以「無資料」姿態呈現。
_NO_DATA_STATUS = ProtocolStatus(
    level_code=PROTOCOL_LEVEL_CODE.L0,
    status="no_data",
    drawdown=None,
    current_cumulative_twr=None,
    data_month_count=0,
)


def _container() -> Container:
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染總覽頁：登入後預設落地頁。"""
    st.title("總覽")
    container = _container()

    try:
        latest_ym = container.record_repo.latest_year_month()
        if latest_ym is None:
            _render(status=_NO_DATA_STATUS, current_net_worth=None)
            return

        range_df = container.record_repo.read_range(
            start_ym=EARLIEST_YEAR_MONTH_SENTINEL, end_ym=latest_ym
        )
        holdings = container.holding_repo.list_holdings()
        series = container.return_service.cumulative_twr_series(
            range_df=range_df, holdings=holdings
        )
        thresholds = container.protocol_service.effective_thresholds(
            stored=container.protocol_threshold_repo.read_thresholds()
        )
        status = container.protocol_service.assess(
            series=series, thresholds=thresholds, min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        net_worth_points = container.allocation_service.net_worth_series(
            range_df=range_df, holdings=holdings
        )
        current_net_worth = net_worth_points[-1].net_worth if net_worth_points else None

        _render(status=status, current_net_worth=current_net_worth)
    except AssetLabError as error:
        logger.exception("總覽頁渲染失敗")
        st.error(str(error))


def _render(*, status: ProtocolStatus, current_net_worth: float | None) -> None:
    """依判定結果畫燈號/等級/回撤帶、必做禁止摘要與關鍵指標。"""
    presentation = overview_presentation.resolve_presentation(status)
    spec = presentation.level_spec

    st.subheader(f"{_SIGNAL_EMOJI[spec.code]} {spec.code}　{spec.label}（{spec.band_text}）")

    if presentation.neutral_message is not None:
        st.info(presentation.neutral_message)
    elif presentation.show_alert:
        st.warning(f"目前處於「{spec.label}」，請依協定行動，勿自行判斷。")
    else:
        st.success("目前為平時姿態，照原訂計畫進行。")

    columns = st.columns(2)
    with columns[0]:
        st.markdown("**必做**")
        for item in spec.must_do:
            st.write(f"- {item}")
    with columns[1]:
        st.markdown("**禁止**")
        for item in spec.must_not:
            st.write(f"- {item}")

    metric_columns = st.columns(3)
    metric_columns[0].metric(
        "最新累積 TWR", _format_decimal_as_percent(status.current_cumulative_twr)
    )
    metric_columns[1].metric(
        "目前淨值", "—" if current_net_worth is None else f"{current_net_worth:,.0f}"
    )
    metric_columns[2].metric("目前自高點回撤", _format_percent_value(presentation.drawdown_percent))


def _format_decimal_as_percent(value: float | None) -> str:
    """把小數報酬率（如 0.08 表 8%）格式化為百分比字串；None 顯示破折號。"""
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


def _format_percent_value(value: float | None) -> str:
    """把已換算的百分比數值（如 -25.0 表 -25%）格式化為字串；None 顯示破折號。"""
    if value is None:
        return "—"
    return f"{value:.2f}%"


render()
