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


def _asset_in(holding_id: int, category: str) -> HoldingModel:
    """建立指定分類的資產項目主檔（佔比測試不依賴初始市值/成本）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=f"資產{holding_id}",
        kind="asset",
        category=category,
        initial_market_value=0.0,
        initial_cost=0.0,
    )


def _record(holding_id: int, year_month: str, market_value: float | None) -> MonthlyRecordModel:
    """建立一筆月度紀錄（佔比/漂移口徑不使用淨投入，固定 0）。"""
    return MonthlyRecordModel(
        holding_id=holding_id, year_month=year_month, market_value=market_value
    )


class TestSnapshotWeights:
    """snapshot：選定月份資產佔比（圓餅圖資料層，僅資產）—— SC-025。"""

    @pytest.mark.scenario("SC-025")
    def test_sc025_holding_weights_sum_to_hundred_percent(self):
        # 台積電 530000、現金 470000：分母 1000000 → 53%、47%（佔比以 % 表示）
        holdings = [
            _asset_in(1, ASSET_CATEGORIES.TW_STOCK),
            _asset_in(2, ASSET_CATEGORIES.DEMAND_DEPOSIT),
        ]
        month_records = [_record(1, "2026-05", 530000.0), _record(2, "2026-05", 470000.0)]
        snapshot = AllocationService().snapshot(
            month_records=month_records, holdings=holdings, by="holding"
        )
        weights = {row.dimension_key: row.weight for row in snapshot}
        assert weights["資產1"] == pytest.approx(53.0)
        assert weights["資產2"] == pytest.approx(47.0)
        assert sum(row.weight for row in snapshot) == pytest.approx(100.0)
        # 攜帶該月份與市值供圖表標示
        assert all(row.year_month == "2026-05" for row in snapshot)
        assert {row.dimension_key: row.market_value for row in snapshot}["資產1"] == 530000.0

    @pytest.mark.scenario("SC-025")
    def test_sc025_category_granularity_aggregates_by_category(self):
        # 同分類多項目按分類粒度合併：台股 600000+100000=700000、現金 300000 → 70%、30%
        holdings = [
            _asset_in(1, ASSET_CATEGORIES.TW_STOCK),
            _asset_in(2, ASSET_CATEGORIES.TW_STOCK),
            _asset_in(3, ASSET_CATEGORIES.DEMAND_DEPOSIT),
        ]
        month_records = [
            _record(1, "2026-05", 600000.0),
            _record(2, "2026-05", 100000.0),
            _record(3, "2026-05", 300000.0),
        ]
        snapshot = AllocationService().snapshot(
            month_records=month_records, holdings=holdings, by="category"
        )
        by_category = {row.dimension_key: row for row in snapshot}
        assert by_category[ASSET_CATEGORIES.TW_STOCK].market_value == 700000.0
        assert by_category[ASSET_CATEGORIES.TW_STOCK].weight == pytest.approx(70.0)
        assert by_category[ASSET_CATEGORIES.DEMAND_DEPOSIT].weight == pytest.approx(30.0)

    @pytest.mark.scenario("SC-025")
    def test_sc025_empty_month_yields_empty_snapshot(self):
        # 該月無任何資產紀錄：圓餅圖無任何佔比列
        snapshot = AllocationService().snapshot(
            month_records=[], holdings=[_asset_in(1, ASSET_CATEGORIES.TW_STOCK)], by="holding"
        )
        assert snapshot == []

    @pytest.mark.scenario("SC-025")
    def test_sc025_none_market_value_does_not_contribute(self):
        # 月內列出但市值留空（仍持有未更新）：不貢獻分子，分母僅含有值資產
        holdings = [
            _asset_in(1, ASSET_CATEGORIES.TW_STOCK),
            _asset_in(2, ASSET_CATEGORIES.DEMAND_DEPOSIT),
        ]
        month_records = [_record(1, "2026-05", 800000.0), _record(2, "2026-05", None)]
        snapshot = AllocationService().snapshot(
            month_records=month_records, holdings=holdings, by="holding"
        )
        # 僅資產1（800000）構成分母，獨佔 100%；留空的資產2不出現
        keys = {row.dimension_key for row in snapshot}
        assert keys == {"資產1"}
        assert snapshot[0].weight == pytest.approx(100.0)


class TestDriftSeries:
    """drift_series：各資產分類佔比隨月份變化（堆疊面積圖資料層，僅資產）—— SC-026。"""

    @pytest.mark.scenario("SC-026")
    def test_sc026_category_weights_change_over_months(self):
        # 台股與現金兩分類跨兩月：各月各分類佔比（%），同月總和 100%
        holdings = [
            _asset_in(1, ASSET_CATEGORIES.TW_STOCK),
            _asset_in(2, ASSET_CATEGORIES.DEMAND_DEPOSIT),
        ]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-03", "market_value": 600000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-03", "market_value": 400000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-04", "market_value": 800000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-04", "market_value": 200000.0,
                 "net_investment": 0.0},
            ]
        )
        drift = AllocationService().drift_series(range_df=range_df, holdings=holdings)
        # 以「年月 × 分類」長表呈現各月各分類佔比
        cell = {
            (row.year_month, row.dimension_key): row.weight for row in drift.itertuples(index=False)
        }
        assert cell[("2026-03", ASSET_CATEGORIES.TW_STOCK)] == pytest.approx(60.0)
        assert cell[("2026-03", ASSET_CATEGORIES.DEMAND_DEPOSIT)] == pytest.approx(40.0)
        # 次月台股佔比上升、現金下降，反映配置漂移
        assert cell[("2026-04", ASSET_CATEGORIES.TW_STOCK)] == pytest.approx(80.0)
        assert cell[("2026-04", ASSET_CATEGORIES.DEMAND_DEPOSIT)] == pytest.approx(20.0)

    @pytest.mark.scenario("SC-026")
    def test_sc026_nodes_are_data_months_with_gap_skipped(self):
        # 2026-04 整月缺漏：節點只取有資料月，缺月不補點
        holdings = [_asset_in(1, ASSET_CATEGORIES.TW_STOCK)]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-03", "market_value": 600000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-05", "market_value": 700000.0,
                 "net_investment": 0.0},
            ]
        )
        drift = AllocationService().drift_series(range_df=range_df, holdings=holdings)
        assert sorted(drift["year_month"].unique()) == ["2026-03", "2026-05"]

    @pytest.mark.scenario("SC-026")
    def test_sc026_liabilities_excluded(self):
        # 漂移圖僅含資產分類：負債不形成任何分類列
        holdings = [
            _asset_in(1, ASSET_CATEGORIES.TW_STOCK),
            HoldingModel(holding_id=2, name="信用卡", kind="liability", category=None,
                         initial_market_value=None, initial_cost=None),
        ]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-03", "market_value": 500000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-03", "market_value": 200000.0,
                 "net_investment": 0.0},
            ]
        )
        drift = AllocationService().drift_series(range_df=range_df, holdings=holdings)
        assert set(drift["dimension_key"].unique()) == {ASSET_CATEGORIES.TW_STOCK}
        # 分母僅資產 500000，台股獨佔 100%
        assert drift.iloc[0]["weight"] == pytest.approx(100.0)

    @pytest.mark.scenario("SC-026")
    def test_sc026_empty_range_yields_empty_frame(self):
        # 區間內無資料：漂移面積圖無任何節點
        drift = AllocationService().drift_series(
            range_df=_range_df([]), holdings=[_asset_in(1, ASSET_CATEGORIES.TW_STOCK)]
        )
        assert drift.empty


class TestZeroTotalAssetWeight:
    """SC-036：某月資產市值合計為 0 時，佔比圖略過該月。

    該月佔比分母為 0 無法定義，略過不產生任何佔比節點（與缺月一致），
    其餘有效月份照常呈現；淨值序列仍含該月（相減不受影響）。
    """

    @pytest.mark.scenario("SC-036")
    def test_sc036_snapshot_skips_month_with_zero_total(self):
        # 該月所有資產市值皆為 0（全數出清）：snapshot 不產生任何佔比列
        holdings = [
            _asset_in(1, ASSET_CATEGORIES.TW_STOCK),
            _asset_in(2, ASSET_CATEGORIES.DEMAND_DEPOSIT),
        ]
        month_records = [_record(1, "2026-05", 0.0), _record(2, "2026-05", 0.0)]
        snapshot = AllocationService().snapshot(
            month_records=month_records, holdings=holdings, by="holding"
        )
        assert snapshot == []

    @pytest.mark.scenario("SC-036")
    def test_sc036_drift_series_skips_zero_total_month_keeps_others(self):
        # 2026-03 全數出清（合計 0）→ 略過該月；2026-04 正常 → 照常呈現
        holdings = [
            _asset_in(1, ASSET_CATEGORIES.TW_STOCK),
            _asset_in(2, ASSET_CATEGORIES.DEMAND_DEPOSIT),
        ]
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-03", "market_value": 0.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-03", "market_value": 0.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-04", "market_value": 800000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-04", "market_value": 200000.0,
                 "net_investment": 0.0},
            ]
        )
        drift = AllocationService().drift_series(range_df=range_df, holdings=holdings)
        # 合計為 0 的 2026-03 不出現；2026-04 正常呈現
        assert sorted(drift["year_month"].unique()) == ["2026-04"]
