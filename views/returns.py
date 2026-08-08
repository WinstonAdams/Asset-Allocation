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
from asset_lab.bootstrap import Container
from asset_lab.core.constants import EARLIEST_YEAR_MONTH_SENTINEL, PERIOD_MODE
from asset_lab.core.exceptions import AssetLabError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.results import ReturnResult
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.services.period_service import PeriodService

logger = logging.getLogger(__name__)

# MWR 無法收斂時的降級顯示文字（與資料層的 not_converged 狀態對應）。
_MWR_UNAVAILABLE = "無法計算"

# 報酬維度的中文顯示（內部值需與 ReturnService.compute_returns(dimension=...) 的合約一致）。
_DIMENSION_LABEL = {"overall": "整體", "category": "分類", "holding": "單一標的"}

# 區間模式的中文顯示（內部值為 PERIOD_MODE 的英文代碼，需與其保持一致）。
_PERIOD_MODE_LABEL = {
    PERIOD_MODE.INCEPTION: "自開始記錄以來",
    PERIOD_MODE.YTD: "今年以來",
    PERIOD_MODE.LAST_12M: "近一年",
    PERIOD_MODE.CUSTOM: "自訂",
}

# 卡片底色：以 MWR 正負判斷（MWR 反映使用者自己這筆錢實際的賺賠，比 TWR 更貼近
# 「我到底賺還是賠」的直覺），正為淺紅、負為淺綠（台股慣例：紅漲綠跌）；MWR 為 0
# 或無法判定（資料不足/不收斂）皆視為中性，用淺灰。皆帶透明感＋細邊框。
_POSITIVE_BACKGROUND = "rgba(220, 38, 38, 0.12)"
_POSITIVE_BORDER = "rgba(220, 38, 38, 0.35)"
_NEGATIVE_BACKGROUND = "rgba(22, 163, 74, 0.12)"
_NEGATIVE_BORDER = "rgba(22, 163, 74, 0.35)"
_NEUTRAL_BACKGROUND = "rgba(148, 163, 184, 0.12)"
_NEUTRAL_BORDER = "rgba(148, 163, 184, 0.35)"
_CARD_TEXT_COLOR = "#1a1a1a"

# TWR/MWR 說明改置頁面底部注解，不逐格掛 tooltip（見 _render_footnote）。
_TWR_FOOTNOTE = (
    "**TWR（時間加權報酬率）**：只看市場漲跌本身的表現，不管你自己存錢、領錢的"
    "時間點，適合拿來跟大盤或其他標的比較績效好壞。"
)
_MWR_FOOTNOTE = (
    "**MWR（金錢加權報酬率）**：算的是「這筆錢在你手上真正賺賠多少」，跟你什麼"
    "時候存錢、什麼時候領錢有關——同一個標的，你跟別人進出場時間不同，算出來的"
    "MWR 就會不一樣。"
)


def _container() -> Container:
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
            "維度",
            options=["overall", "category", "holding"],
            format_func=lambda option: _DIMENSION_LABEL[option],
            horizontal=True,
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
        _render_results(results, holdings=holdings)
        _render_footnote()
    except AssetLabError as error:
        logger.exception("報酬率頁渲染失敗")
        st.error(str(error))


def _resolve_period(
    *, period_service: PeriodService, record_repo: RecordRepository, latest_ym: str
) -> tuple[str, str]:
    """讀區間模式與自訂起訖，委派 PeriodService 解析為 (起月, 訖月)。"""
    mode = st.selectbox(
        "區間",
        options=list(PERIOD_MODE.ALL),
        format_func=lambda option: _PERIOD_MODE_LABEL[option],
    )
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


def _render_results(results: list[ReturnResult], *, holdings: list[HoldingModel]) -> None:
    """逐維度以卡片呈現報酬率；MWR 不收斂時降級為「無法計算」。

    holding 維度的 dimension_key 為穩定的 holding_id 字串（非顯示用），呈現時對照
    主檔轉換為目前名稱；分類維度的 dimension_key 本身即中文分類名，直接顯示。
    卡片底色依 MWR 正負決定——MWR 反映使用者自己這筆錢實際的賺賠，比只看市場
    表現的 TWR 更貼近「我到底賺還是賠」；MWR 為 0 或無法判定（資料不足/不收斂）
    皆視為中性，維持灰色。
    """
    if not results:
        st.write("此區間無可計算的資產報酬。")
        return

    name_by_id = {str(h.holding_id): h.name for h in holdings}
    cards = []
    for index, result in enumerate(results):
        if result.dimension == "holding":
            label = name_by_id.get(result.dimension_key, result.dimension_key)
        else:
            label = result.dimension_key or "整體"
        cards.append((f"return_card_{index}", label, result))

    st.markdown(
        "<style>"
        + "".join(_card_style(key, *_card_colors(result.mwr)) for key, _, result in cards)
        + "</style>",
        unsafe_allow_html=True,
    )
    for key, label, result in cards:
        _render_card(key=key, label=label, result=result)


def _render_card(*, key: str, label: str, result: ReturnResult) -> None:
    """渲染單一維度的卡片：標題 + 四個指標，底色依 MWR 正負決定。"""
    with st.container(key=key):
        st.markdown(f"#### {label}")
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


def _render_footnote() -> None:
    """頁面底部注解：說明 TWR/MWR 的意思，取代逐格 tooltip。"""
    st.divider()
    st.caption(_TWR_FOOTNOTE)
    st.caption(_MWR_FOOTNOTE)


def _card_colors(mwr: float | None) -> tuple[str, str]:
    """依 MWR 正負決定卡片背景與邊框色：正為淺紅、負為淺綠（台股慣例：紅漲綠跌）；
    MWR 為 0 或無法判定（資料不足/不收斂）時為中性灰。
    """
    if mwr is None or mwr == 0:
        return _NEUTRAL_BACKGROUND, _NEUTRAL_BORDER
    if mwr > 0:
        return _POSITIVE_BACKGROUND, _POSITIVE_BORDER
    return _NEGATIVE_BACKGROUND, _NEGATIVE_BORDER


def _card_style(key: str, background: str, border: str) -> str:
    """組出卡片背景/邊框/文字色的 CSS，以 st.container(key=...) 產生的 st-key-{key} class 定位。"""
    return (
        f".st-key-{key} {{ background-color: {background}; border: 1px solid {border}; "
        f"border-radius: 0.5rem; padding: 1rem 1rem 0.25rem 1rem; margin-bottom: 1rem; }}"
        f".st-key-{key} [data-testid='stMetricValue'], "
        f".st-key-{key} [data-testid='stMetricLabel'] {{ color: {_CARD_TEXT_COLOR}; }}"
    )


def _format_percent(value: float | None) -> str:
    """把報酬率小數格式化為百分比字串；None 顯示破折號。"""
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


render()
