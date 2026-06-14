"""charts.py 的 Plotly 圖表元件測試。

圖表元件為純函式：吃資料層（t05）已算好的 Result model / DataFrame，回傳 Plotly Figure，
不碰 st.* 也不做業務運算。本層只驗證「呈現契約」——SC-025~028 規定圓餅只含資產佔比、
堆疊面積以佔比（百分比）呈現各分類隨月份變化、淨值折線可選擇疊加總資產/總負債線、
報酬走勢固定只畫一條累積 TWR 折線。Figure 結構（trace 型別、資料值、堆疊正規化）皆可斷言，
故走完整 RED→GREEN，繫於對應的呈現 SC marker。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pandas as pd
import plotly.graph_objects as go
import pytest

# ==== 專案內部 ====
from asset_lab import charts
from asset_lab.models.results import AllocationSnapshot, CumulativeTwrPoint, NetWorthPoint


@pytest.mark.scenario("SC-025")
def test_sc025_pie_uses_only_asset_weights() -> None:
    """圓餅圖以資產佔比為扇形：標籤與數值取自 snapshot（資料層已排除負債）。"""
    snapshot = [
        AllocationSnapshot(
            year_month="2026-05", dimension_key="台積電", market_value=530000, weight=53.0
        ),
        AllocationSnapshot(
            year_month="2026-05", dimension_key="現金", market_value=470000, weight=47.0
        ),
    ]

    figure = charts.allocation_pie(snapshot=snapshot)

    assert isinstance(figure, go.Figure)
    pie = figure.data[0]
    assert pie.type == "pie"
    assert list(pie.labels) == ["台積電", "現金"]
    assert list(pie.values) == [53.0, 47.0]


@pytest.mark.scenario("SC-025")
def test_sc025_pie_empty_snapshot_renders_without_data() -> None:
    """選定月無有效資產佔比（資料層回空）時，圓餅圖不崩、回無扇形的 Figure。"""
    figure = charts.allocation_pie(snapshot=[])

    assert isinstance(figure, go.Figure)
    assert len(figure.data[0].labels) == 0


@pytest.mark.scenario("SC-026")
def test_sc026_area_is_percent_stacked_by_category_over_months() -> None:
    """堆疊面積圖以佔比（百分比正規化）呈現各分類隨月份變化，每分類一條面積。"""
    drift_df = pd.DataFrame(
        {
            "year_month": ["2026-04", "2026-04", "2026-05", "2026-05"],
            "dimension_key": ["台股/台股ETF", "現金/定存", "台股/台股ETF", "現金/定存"],
            "weight": [60.0, 40.0, 70.0, 30.0],
        }
    )

    figure = charts.allocation_area(drift_df=drift_df)

    assert isinstance(figure, go.Figure)
    # 每個資產分類一條堆疊面積 trace
    categories = {trace.name for trace in figure.data}
    assert categories == {"台股/台股ETF", "現金/定存"}
    # 以百分比堆疊正規化（groupnorm=percent）且確為堆疊（同一 stackgroup）的面積
    for trace in figure.data:
        assert trace.type == "scatter"
        assert trace.groupnorm == "percent"
        assert trace.stackgroup is not None


@pytest.mark.scenario("SC-026")
def test_sc026_area_empty_renders_without_data() -> None:
    """無有效資產分類資料時，堆疊面積圖不崩、回無 trace 的 Figure。"""
    empty = pd.DataFrame(columns=["year_month", "dimension_key", "weight"])

    figure = charts.allocation_area(drift_df=empty)

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 0


@pytest.mark.scenario("SC-027")
def test_sc027_net_worth_line_defaults_to_net_worth_only() -> None:
    """淨值折線預設只畫淨值一條（總資產 − 總負債），不疊加總資產/總負債。"""
    points = [
        NetWorthPoint(
            year_month="2026-04", total_assets=1000, total_liabilities=200, net_worth=800
        ),
        NetWorthPoint(
            year_month="2026-05", total_assets=1200, total_liabilities=150, net_worth=1050
        ),
    ]

    figure = charts.net_worth_line(points=points)

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 1
    net = figure.data[0]
    assert list(net.x) == ["2026-04", "2026-05"]
    assert list(net.y) == [800.0, 1050.0]


@pytest.mark.scenario("SC-027")
def test_sc027_net_worth_line_can_overlay_assets_and_liabilities() -> None:
    """使用者選擇疊加時，淨值折線額外畫出總資產線與總負債線。"""
    points = [
        NetWorthPoint(
            year_month="2026-04", total_assets=1000, total_liabilities=200, net_worth=800
        ),
        NetWorthPoint(
            year_month="2026-05", total_assets=1200, total_liabilities=150, net_worth=1050
        ),
    ]

    figure = charts.net_worth_line(
        points=points, show_assets=True, show_liabilities=True
    )

    series = {trace.name: list(trace.y) for trace in figure.data}
    assert series["淨值"] == [800.0, 1050.0]
    assert series["總資產"] == [1000.0, 1200.0]
    assert series["總負債"] == [200.0, 150.0]


@pytest.mark.scenario("SC-027")
def test_sc027_net_worth_line_empty_renders_without_data() -> None:
    """無淨值資料時不崩、回無 trace 的 Figure。"""
    figure = charts.net_worth_line(points=[])

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 0


@pytest.mark.scenario("SC-028")
def test_sc028_cumulative_twr_is_single_line() -> None:
    """報酬走勢固定只畫一條累積 TWR 折線（不提供指標切換）。"""
    points = [
        CumulativeTwrPoint(year_month="2026-03", cumulative_twr=0.05),
        CumulativeTwrPoint(year_month="2026-04", cumulative_twr=0.12),
        CumulativeTwrPoint(year_month="2026-05", cumulative_twr=0.331),
    ]

    figure = charts.cumulative_twr_line(points=points)

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 1
    line = figure.data[0]
    assert list(line.x) == ["2026-03", "2026-04", "2026-05"]
    assert list(line.y) == [0.05, 0.12, 0.331]


@pytest.mark.scenario("SC-028")
def test_sc028_cumulative_twr_empty_renders_without_data() -> None:
    """無有資料月（資料層回空序列）時不崩、回無資料點的 Figure。"""
    figure = charts.cumulative_twr_line(points=[])

    assert isinstance(figure, go.Figure)
    # 仍是單一折線 trace，只是沒有資料點
    assert len(figure.data) <= 1
    if figure.data:
        assert len(figure.data[0].x) == 0
