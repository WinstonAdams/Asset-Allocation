"""資產配置頁的接線測試：各項目市值趨勢圖（SC-104）。

比照 test_input_view.py：以 AppTest 載入 views/allocation.py，注入替身 Repository 與
真實的 AllocationService／ReturnService。所有項目與金額皆為虛構值。
"""

# ==== 原生（標準庫） ====
import json
from pathlib import Path
from types import SimpleNamespace

# ==== 第三方套件 ====
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.return_service import ReturnService

APP_DIR = Path(__file__).resolve().parent.parent

_TREND_SUBHEADER = "各項目市值趨勢（折線，單位：萬元）"

# (holding_id, year_month, market_value)
_VALUES = [
    (1, "2026-04", 500000.0),
    (1, "2026-05", 600000.0),
    (1, "2026-06", 580000.0),
    (2, "2026-04", 300000.0),
    (2, "2026-05", 420000.0),
    (2, "2026-06", 450000.0),
    (3, "2026-04", 30000.0),
    (3, "2026-05", 30000.0),
    (3, "2026-06", 30000.0),
]


def _holdings() -> list[HoldingModel]:
    return [
        HoldingModel(holding_id=1, name="活存", kind="asset", category="活存",
                     initial_market_value=0.0, initial_cost=0.0),
        HoldingModel(holding_id=2, name="台積電", kind="asset", category="台股/台股ETF",
                     initial_market_value=0.0, initial_cost=0.0),
        HoldingModel(holding_id=3, name="信用卡", kind="liability", category=None,
                     initial_market_value=None, initial_cost=None),
    ]


class _StubHoldingRepo:
    def list_holdings(self) -> list[HoldingModel]:
        return _holdings()


class _StubRecordRepo:
    def latest_year_month(self) -> str:
        return "2026-06"

    def read_month(self, *, year_month: str) -> list[MonthlyRecordModel]:
        return [
            MonthlyRecordModel(holding_id=hid, year_month=ym, market_value=value)
            for hid, ym, value in _VALUES
            if ym == year_month
        ]

    def read_range(self, *, start_ym: str, end_ym: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"holding_id": hid, "year_month": ym, "market_value": value,
                 "net_investment": 0.0, "total_cost": None, "realized_income": None,
                 "cash_dividend": None}
                for hid, ym, value in _VALUES
            ]
        )


class _StubTargetRepo:
    def read_targets(self) -> list:
        return []


def _run_page() -> AppTest:
    at = AppTest.from_file(APP_DIR / "views" / "allocation.py")
    at.session_state["container"] = SimpleNamespace(
        holding_repo=_StubHoldingRepo(),
        record_repo=_StubRecordRepo(),
        target_repo=_StubTargetRepo(),
        allocation_service=AllocationService(),
        return_service=ReturnService(),
    )
    at.run()
    return at


def _trend_figure(at: AppTest) -> dict:
    """取各項目市值趨勢圖：頁上折線名稱恰為「活存」「台積電」（項目名）的那張圖。

    其他圖的折線名為「淨值」「累積 TWR」或分類名（面積圖的「活存」是分類），不會同時符合。
    """
    figures = [json.loads(chart.proto.spec) for chart in at.get("plotly_chart")]
    matched = [
        figure
        for figure in figures
        if [trace.get("name") for trace in figure["data"]] == ["活存", "台積電"]
        and all(trace.get("type") == "scatter" for trace in figure["data"])
        and all(trace.get("connectgaps") is False for trace in figure["data"])
    ]
    assert len(matched) == 1
    return matched[0]


class TestHoldingValueTrendOnPage:
    @pytest.mark.scenario("SC-104")
    def test_page_shows_trend_chart_with_one_line_per_asset_in_wan(self):
        at = _run_page()

        assert not at.exception
        assert _TREND_SUBHEADER in [s.value for s in at.subheader]
        figure = _trend_figure(at)
        traces = {trace["name"]: trace for trace in figure["data"]}
        assert list(traces) == ["活存", "台積電"]
        assert traces["活存"]["x"] == ["2026-04", "2026-05", "2026-06"]
        assert traces["活存"]["y"] == [50.0, 60.0, 58.0]
        assert traces["台積電"]["y"] == [30.0, 42.0, 45.0]
