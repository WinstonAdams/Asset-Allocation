# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pandas as pd
import pytest

# ==== 專案內部 ====
from asset_lab.models.holding import HoldingModel
from asset_lab.services.return_service import ReturnService


def _range_df(rows: list[dict]) -> pd.DataFrame:
    """以 (holding_id, year_month, market_value, net_investment) 列組成區間 DataFrame。"""
    return pd.DataFrame(
        rows, columns=["holding_id", "year_month", "market_value", "net_investment"]
    )


def _asset(holding_id: int, initial_market_value: float) -> HoldingModel:
    """建立一個資產項目主檔，初始成本與初始市值一致以便對齊 TWR 起點。"""
    return HoldingModel(
        holding_id=holding_id,
        name=f"資產{holding_id}",
        kind="asset",
        category="台股/台股ETF",
        initial_market_value=initial_market_value,
        initial_cost=initial_market_value,
    )


def _liability(holding_id: int) -> HoldingModel:
    """建立一個負債項目主檔（不應進入報酬走勢）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=f"負債{holding_id}",
        kind="liability",
        category=None,
        initial_market_value=None,
        initial_cost=None,
    )


def _approx(value: float, expected: float) -> bool:
    """以浮點容差比較累積報酬率。"""
    return value == pytest.approx(expected, abs=1e-9)


class TestCumulativeTwrSeries:
    """cumulative_twr_series：供報酬率走勢圖的逐有資料月累積 TWR 折線（僅資產）。"""

    @pytest.mark.scenario("SC-028")
    def test_sc028_one_point_per_data_month(self):
        # 整體初始市值 100000，連續三月各漲 10%：每個有資料月一個累積 TWR 點
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-01", "market_value": 110000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-02", "market_value": 121000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-03", "market_value": 133100.0,
                 "net_investment": 0.0},
            ]
        )
        series = ReturnService().cumulative_twr_series(
            range_df=range_df, holdings=[_asset(1, 100000.0)]
        )
        # 三個有資料月各一點，累積 TWR 逐月為 10%、21%、33.1%
        assert [point.year_month for point in series] == ["2026-01", "2026-02", "2026-03"]
        assert _approx(series[0].cumulative_twr, 0.10)
        assert _approx(series[1].cumulative_twr, 0.21)
        assert _approx(series[2].cumulative_twr, 0.331)

    @pytest.mark.scenario("SC-028")
    def test_sc028_nodes_are_data_months_with_gap_skipped(self):
        # 2026-03 整月缺漏：走勢圖節點只取有資料月，缺月不補點
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-01", "market_value": 110000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-02", "market_value": 121000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-04", "market_value": 133100.0,
                 "net_investment": 0.0},
            ]
        )
        series = ReturnService().cumulative_twr_series(
            range_df=range_df, holdings=[_asset(1, 100000.0)]
        )
        assert [point.year_month for point in series] == ["2026-01", "2026-02", "2026-04"]
        assert _approx(series[-1].cumulative_twr, 0.331)

    @pytest.mark.scenario("SC-028")
    def test_sc028_liabilities_excluded_from_series(self):
        # 走勢圖僅含資產：負債列不影響累積 TWR
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-01", "market_value": 110000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-01", "market_value": 500000.0,
                 "net_investment": 0.0},
            ]
        )
        series = ReturnService().cumulative_twr_series(
            range_df=range_df, holdings=[_asset(1, 100000.0), _liability(2)]
        )
        # 僅資產項目 1（100000→110000）貢獻，累積 TWR 10%
        assert len(series) == 1
        assert _approx(series[0].cumulative_twr, 0.10)

    @pytest.mark.scenario("SC-028")
    def test_sc028_empty_range_yields_empty_series(self):
        # 區間內無資料：走勢圖無任何節點
        series = ReturnService().cumulative_twr_series(
            range_df=_range_df([]), holdings=[_asset(1, 100000.0)]
        )
        assert series == []
