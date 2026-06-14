# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pandas as pd
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.services.allocation_service import AllocationService


def _range_df(rows: list[dict]) -> pd.DataFrame:
    """以 (holding_id, year_month, market_value, net_investment) 列組成區間 DataFrame。"""
    return pd.DataFrame(
        rows, columns=["holding_id", "year_month", "market_value", "net_investment"]
    )


def _asset(holding_id: int, category: str = "台股/台股ETF") -> HoldingModel:
    """建立一個資產項目主檔。"""
    return HoldingModel(
        holding_id=holding_id,
        name=f"資產{holding_id}",
        kind="asset",
        category=category,
        initial_market_value=0.0,
        initial_cost=0.0,
    )


def _liability(holding_id: int) -> HoldingModel:
    """建立一個負債項目主檔（不歸類、無初始市值/成本）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=f"負債{holding_id}",
        kind="liability",
        category=None,
        initial_market_value=None,
        initial_cost=None,
    )


def _record(holding_id: int, year_month: str, market_value: float | None) -> MonthlyRecordModel:
    """建立一筆月度紀錄；淨投入與淨值口徑無關，固定 0。"""
    return MonthlyRecordModel(
        holding_id=holding_id, year_month=year_month, market_value=market_value
    )


class TestNetWorthSeries:
    """net_worth_series：淨值＝總資產 − 總負債的跨月趨勢（SC-010/011/027 資料層）。"""

    @pytest.mark.scenario("SC-010")
    def test_sc010_net_worth_is_assets_minus_liabilities(self):
        # 台積電 530000 + 現金 470000 = 總資產 1000000；信用卡 200000 = 總負債
        holdings = [
            _asset(1, "台股/台股ETF"),
            _asset(2, "現金/定存"),
            _liability(3),
        ]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-05", "market_value": 530000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-05", "market_value": 470000.0,
                 "net_investment": 0.0},
                {"holding_id": 3, "year_month": "2026-05", "market_value": 200000.0,
                 "net_investment": 0.0},
            ]
        )
        series = AllocationService().net_worth_series(range_df=range_df, holdings=holdings)
        assert len(series) == 1
        point = series[0]
        assert point.year_month == "2026-05"
        assert point.total_assets == 1000000.0
        assert point.total_liabilities == 200000.0
        # 淨值 = 總資產 1000000 − 總負債 200000
        assert point.net_worth == 800000.0

    @pytest.mark.scenario("SC-010")
    def test_sc010_no_liability_means_net_worth_equals_assets(self):
        # 無任何負債項目時，淨值等於總資產（總負債為 0）
        holdings = [_asset(1, "台股/台股ETF"), _asset(2, "現金/定存")]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-05", "market_value": 530000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-05", "market_value": 470000.0,
                 "net_investment": 0.0},
            ]
        )
        series = AllocationService().net_worth_series(range_df=range_df, holdings=holdings)
        assert series[0].total_liabilities == 0.0
        assert series[0].net_worth == series[0].total_assets == 1000000.0

    @pytest.mark.scenario("SC-010")
    def test_sc010_net_worth_can_be_negative_when_liabilities_exceed_assets(self):
        # 負債大於資產：淨值為負數（淨值公式不設下限）
        holdings = [_asset(1, "現金/定存"), _liability(2)]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-05", "market_value": 100000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-05", "market_value": 300000.0,
                 "net_investment": 0.0},
            ]
        )
        series = AllocationService().net_worth_series(range_df=range_df, holdings=holdings)
        # 淨值 = 100000 − 300000 = −200000
        assert series[0].net_worth == -200000.0

    @pytest.mark.scenario("SC-027")
    def test_sc027_one_point_per_data_month_in_order(self):
        # 跨多月：每個有資料月一個淨值點，依月份排序，攜帶總資產/總負債供疊加
        holdings = [_asset(1, "台股/台股ETF"), _liability(2)]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-03", "market_value": 800000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-03", "market_value": 100000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-04", "market_value": 900000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-04", "market_value": 150000.0,
                 "net_investment": 0.0},
            ]
        )
        series = AllocationService().net_worth_series(range_df=range_df, holdings=holdings)
        assert [p.year_month for p in series] == ["2026-03", "2026-04"]
        # 各月攜帶總資產線與總負債線供圖表疊加
        assert (series[0].total_assets, series[0].total_liabilities) == (800000.0, 100000.0)
        assert (series[1].total_assets, series[1].total_liabilities) == (900000.0, 150000.0)
        assert series[0].net_worth == 700000.0
        assert series[1].net_worth == 750000.0

    @pytest.mark.scenario("SC-027")
    def test_sc027_nodes_are_data_months_with_gap_skipped(self):
        # 2026-04 整月缺漏：節點只取有資料月，缺月不補點
        holdings = [_asset(1, "台股/台股ETF")]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-03", "market_value": 800000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-05", "market_value": 900000.0,
                 "net_investment": 0.0},
            ]
        )
        series = AllocationService().net_worth_series(range_df=range_df, holdings=holdings)
        assert [p.year_month for p in series] == ["2026-03", "2026-05"]

    @pytest.mark.scenario("SC-027")
    def test_sc027_empty_range_yields_empty_series(self):
        # 區間內無資料：無任何淨值節點
        series = AllocationService().net_worth_series(
            range_df=_range_df([]), holdings=[_asset(1, "台股/台股ETF")]
        )
        assert series == []


class TestLiabilityExcludedFromWeights:
    """SC-011：負債排除於配置佔比之外（佔比分母/分子皆僅含資產）。"""

    @pytest.mark.scenario("SC-011")
    def test_sc011_liability_excluded_from_holding_weights(self):
        # 同月有資產與一筆負債：佔比分母僅資產 1000000，負債不出現也不稀釋
        holdings = [
            _asset(1, "台股/台股ETF"),
            _asset(2, "現金/定存"),
            _liability(3),
        ]
        month_records = [
            _record(1, "2026-05", 530000.0),
            _record(2, "2026-05", 470000.0),
            _record(3, "2026-05", 200000.0),
        ]
        snapshot = AllocationService().snapshot(
            month_records=month_records, holdings=holdings, by="holding"
        )
        keys = {row.dimension_key for row in snapshot}
        # 負債項目不在任何佔比列中
        assert "負債3" not in keys and "資產3" not in keys
        # 佔比分母僅由資產組成，總和為 100%
        assert sum(row.weight for row in snapshot) == pytest.approx(100.0)

    @pytest.mark.scenario("SC-011")
    def test_sc011_liability_excluded_from_category_weights(self):
        # 按分類彙總時，負債（分類為 None）不形成任何分類佔比列
        holdings = [
            _asset(1, ASSET_CATEGORIES.TW_STOCK),
            _asset(2, ASSET_CATEGORIES.CASH),
            _liability(3),
        ]
        month_records = [
            _record(1, "2026-05", 600000.0),
            _record(2, "2026-05", 400000.0),
            _record(3, "2026-05", 999999.0),
        ]
        snapshot = AllocationService().snapshot(
            month_records=month_records, holdings=holdings, by="category"
        )
        categories = {row.dimension_key for row in snapshot}
        assert categories == {ASSET_CATEGORIES.TW_STOCK, ASSET_CATEGORIES.CASH}
        # 分母僅資產 1000000：台股 60%、現金 40%
        weights = {row.dimension_key: row.weight for row in snapshot}
        assert weights[ASSET_CATEGORIES.TW_STOCK] == pytest.approx(60.0)
        assert weights[ASSET_CATEGORIES.CASH] == pytest.approx(40.0)
