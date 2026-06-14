"""Plotly 圖表元件層。

把資料層（配置/報酬服務）算好的 Result model 與 DataFrame 轉成 Plotly Figure，供 Page
以 st.plotly_chart 渲染。本層為純函式：不碰 st.*、不碰 I/O、不做業務運算，只負責呈現契約。

呈現契約對應四張圖：
- 配置圓餅：選定月份資產佔比，僅資產（負債已由資料層排除）。
- 配置漂移堆疊面積：各資產分類佔比隨月份變化，以百分比堆疊正規化呈現。
- 淨值折線：跨月淨值趨勢，預設只畫淨值；使用者可選擇疊加總資產線與總負債線。
- 報酬率走勢：固定只畫一條累積 TWR 折線，不提供指標切換。

所有輸入可能為空（選定月無有效資產佔比、區間無有資料月等），一律回傳無資料的 Figure
而非報錯，讓 Page 仍能安全渲染空圖。
"""

# ==== 原生（標準庫） ====
from collections.abc import Sequence

# ==== 第三方套件 ====
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ==== 專案內部 ====
from asset_lab.models.results import AllocationSnapshot, CumulativeTwrPoint, NetWorthPoint

# 堆疊面積圖各分類面積的長表欄位（與 AllocationService.drift_series 輸出一致）。
_AREA_YEAR_MONTH = "year_month"
_AREA_DIMENSION_KEY = "dimension_key"
_AREA_WEIGHT = "weight"

# 淨值折線三條線的圖例名稱。
_NET_WORTH_LABEL = "淨值"
_TOTAL_ASSETS_LABEL = "總資產"
_TOTAL_LIABILITIES_LABEL = "總負債"


def allocation_pie(*, snapshot: Sequence[AllocationSnapshot]) -> go.Figure:
    """以選定月份的資產配置佔比畫圓餅圖（僅資產）。

    扇形的標籤與數值取自資料層算好的 snapshot（負債已於資料層排除）；snapshot 為空
    （選定月無有效資產市值）時回傳無扇形的 Figure，使 Page 仍能安全渲染。

    Args:
        snapshot: 選定月份的配置佔比清單，每筆含維度鍵（項目名或分類）與佔比（%）。

    Returns:
        Plotly 圓餅圖 Figure。
    """
    labels = [item.dimension_key for item in snapshot]
    values = [item.weight for item in snapshot]
    return px.pie(names=labels, values=values)


def allocation_area(*, drift_df: pd.DataFrame) -> go.Figure:
    """以各資產分類佔比隨月份變化畫百分比堆疊面積圖（僅資產）。

    每個資產分類一條堆疊面積，x 為有資料月、y 為該分類當月佔比；以百分比堆疊正規化
    （groupnorm="percent"）呈現各分類相對結構隨月份的變化。資料為空時回傳無 trace 的
    Figure。

    Args:
        drift_df: 長表 DataFrame，欄為 year_month、dimension_key（分類）、weight（%）；
            即 AllocationService.drift_series 的輸出。

    Returns:
        Plotly 堆疊面積圖 Figure。
    """
    if drift_df.empty:
        return go.Figure()
    return px.area(
        drift_df,
        x=_AREA_YEAR_MONTH,
        y=_AREA_WEIGHT,
        color=_AREA_DIMENSION_KEY,
        groupnorm="percent",
    )


def net_worth_line(
    *,
    points: Sequence[NetWorthPoint],
    show_assets: bool = False,
    show_liabilities: bool = False,
) -> go.Figure:
    """以跨月淨值趨勢畫折線圖，可選擇疊加總資產線與總負債線。

    預設只畫淨值一條（總資產 − 總負債）；show_assets / show_liabilities 為 True 時各
    額外疊加一條對應折線。points 為空時回傳無 trace 的 Figure。

    Args:
        points: 跨月淨值序列，每筆含年月、總資產、總負債、淨值；即 net_worth_series 輸出。
        show_assets: 是否疊加總資產線。
        show_liabilities: 是否疊加總負債線。

    Returns:
        Plotly 折線圖 Figure。
    """
    figure = go.Figure()
    if not points:
        return figure

    months = [point.year_month for point in points]
    figure.add_trace(
        go.Scatter(
            x=months,
            y=[point.net_worth for point in points],
            mode="lines+markers",
            name=_NET_WORTH_LABEL,
        )
    )
    if show_assets:
        figure.add_trace(
            go.Scatter(
                x=months,
                y=[point.total_assets for point in points],
                mode="lines+markers",
                name=_TOTAL_ASSETS_LABEL,
            )
        )
    if show_liabilities:
        figure.add_trace(
            go.Scatter(
                x=months,
                y=[point.total_liabilities for point in points],
                mode="lines+markers",
                name=_TOTAL_LIABILITIES_LABEL,
            )
        )
    return figure


def cumulative_twr_line(*, points: Sequence[CumulativeTwrPoint]) -> go.Figure:
    """以逐有資料月的累積 TWR 畫單一折線（不提供指標切換）。

    固定只畫累積 TWR 一條折線，x 為有資料月、y 為自區間起點累積至該月的 TWR；其他報酬
    指標（MWR、簡單總報酬率）僅以數字呈現，不進此走勢圖。points 為空時回傳無資料點的
    Figure。

    Args:
        points: 逐有資料月的累積 TWR 序列；即 ReturnService.cumulative_twr_series 輸出。

    Returns:
        Plotly 折線圖 Figure（單一 trace）。
    """
    months = [point.year_month for point in points]
    values = [point.cumulative_twr for point in points]
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=months, y=values, mode="lines+markers"))
    return figure
