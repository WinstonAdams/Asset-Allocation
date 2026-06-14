# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pandas as pd
import pytest

# ==== 專案內部 ====
from asset_lab.services.return_service import ReturnService


def _monthly(rows: list[dict]) -> pd.DataFrame:
    """以 (year_month, market_value, net_investment) 列組成月度序列 DataFrame。

    Args:
        rows: 每列為含 year_month、market_value、net_investment 鍵的 dict；
            market_value 可為 None 表當月留空（仍持有未更新）。

    Returns:
        欄位齊全的月度序列 DataFrame。
    """
    return pd.DataFrame(rows, columns=["year_month", "market_value", "net_investment"])


def _approx(value: float | None, expected: float) -> bool:
    """以浮點容差比較報酬率（百分比小數，如 0.331）。"""
    return value is not None and value == pytest.approx(expected, abs=1e-9)


class TestComputeTwr:
    """compute_twr：時間加權報酬率，逐段連乘且排除當月淨投入。"""

    @pytest.mark.scenario("SC-012")
    def test_sc012_chain_links_periods_excluding_net_investment(self):
        # 初始市值 100000，連續三月各漲 10% 且無資金流動
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 110000.0, "net_investment": 0.0},
                {"year_month": "2026-02", "market_value": 121000.0, "net_investment": 0.0},
                {"year_month": "2026-03", "market_value": 133100.0, "net_investment": 0.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=100000.0)
        # (1.10 × 1.10 × 1.10) − 1 = 33.1%
        assert _approx(twr, 0.331)

    @pytest.mark.scenario("SC-013")
    def test_sc013_extra_capital_not_counted_as_return(self):
        # 期初 100000，當月投入 50000、市值漲到 155000（市場僅貢獻 5000）
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 155000.0, "net_investment": 50000.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=100000.0)
        # (155000 − 50000 − 100000) ÷ 100000 = 5%；裸算 55% 為錯誤
        assert _approx(twr, 0.05)

    @pytest.mark.scenario("SC-013")
    def test_sc013_naive_end_over_begin_would_be_wrong(self):
        # 防呆對照：未排除淨投入會誤得 55%
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 155000.0, "net_investment": 50000.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=100000.0)
        assert twr != pytest.approx(0.55)

    @pytest.mark.scenario("SC-014")
    def test_sc014_zero_opening_building_month_excluded(self):
        # 建倉月期初市值 0：該段不納入連乘，自下一個期初大於 0 的期間起算
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 100000.0, "net_investment": 100000.0},
                {"year_month": "2026-02", "market_value": 110000.0, "net_investment": 0.0},
                {"year_month": "2026-03", "market_value": 121000.0, "net_investment": 0.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=0.0)
        # 建倉段 (0→100000) 跳過；其後 (100000→110000→121000) = 1.1×1.1 − 1 = 21%
        assert _approx(twr, 0.21)

    @pytest.mark.scenario("SC-014")
    def test_sc014_all_segments_excluded_yields_none(self):
        # 期初 0 且僅有建倉月一段：無有效連乘段，無從計算 TWR
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 100000.0, "net_investment": 100000.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=0.0)
        assert twr is None

    @pytest.mark.scenario("SC-014")
    def test_sc014_empty_series_yields_none(self):
        # 無任何有資料月：無連乘段
        twr = ReturnService().compute_twr(monthly=_monthly([]), initial_market_value=100000.0)
        assert twr is None

    @pytest.mark.scenario("SC-022")
    def test_sc022_gap_month_segmented_not_filled(self):
        # 2026-03 整月缺漏；以相鄰有資料月 2026-02 與 2026-04 直接成一段
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 110000.0, "net_investment": 0.0},
                {"year_month": "2026-02", "market_value": 121000.0, "net_investment": 0.0},
                {"year_month": "2026-04", "market_value": 133100.0, "net_investment": 0.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=100000.0)
        # 缺月不補插：(100000→110000→121000→133100) 三段 = 1.1³ − 1 = 33.1%
        assert _approx(twr, 0.331)

    @pytest.mark.scenario("SC-022")
    def test_sc022_unsorted_input_is_ordered_chronologically(self):
        # 亂序輸入仍以時間排序後分段，結果不受列順序影響
        monthly = _monthly(
            [
                {"year_month": "2026-04", "market_value": 133100.0, "net_investment": 0.0},
                {"year_month": "2026-01", "market_value": 110000.0, "net_investment": 0.0},
                {"year_month": "2026-02", "market_value": 121000.0, "net_investment": 0.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=100000.0)
        assert _approx(twr, 0.331)

    @pytest.mark.scenario("SC-024")
    def test_sc024_blank_value_carries_forward_previous_month(self):
        # 2026-05 仍持有但市值留空：沿用 2026-04 的 250000，視為 0% 變動段
        monthly = _monthly(
            [
                {"year_month": "2026-04", "market_value": 250000.0, "net_investment": 0.0},
                {"year_month": "2026-05", "market_value": None, "net_investment": 0.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=250000.0)
        # 留空月沿用 250000：(250000→250000→250000) 皆 0% → TWR 0%
        assert _approx(twr, 0.0)

    @pytest.mark.scenario("SC-024")
    def test_sc024_carry_forward_does_not_count_as_change(self):
        # 沿用值不被視為當月變動：先漲後留空，留空月報酬為 0、不重複計入漲幅
        monthly = _monthly(
            [
                {"year_month": "2026-04", "market_value": 275000.0, "net_investment": 0.0},
                {"year_month": "2026-05", "market_value": None, "net_investment": 0.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=250000.0)
        # (250000→275000) = 10%，(275000→沿用275000) = 0% → TWR 10%
        assert _approx(twr, 0.10)


class TestComputePnl:
    """compute_pnl：賺賠金額與簡單總報酬率，以累積成本起算。"""

    @pytest.mark.scenario("SC-017")
    def test_sc017_pnl_and_simple_return_from_cumulative_cost(self):
        # 初始成本 300000、後續淨投入合計 +100000、當前市值 500000
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 420000.0, "net_investment": 60000.0},
                {"year_month": "2026-02", "market_value": 500000.0, "net_investment": 40000.0},
            ]
        )
        pnl, simple_return = ReturnService().compute_pnl(monthly=monthly, initial_cost=300000.0)
        # 累積成本 300000+100000=400000；賺賠 500000−400000=100000；簡單報酬 25%
        assert pnl == pytest.approx(100000.0)
        assert _approx(simple_return, 0.25)

    @pytest.mark.scenario("SC-017")
    def test_sc017_zero_cumulative_cost_hides_simple_return(self):
        # 累積成本為 0（初始成本 0 且淨投入互抵）：簡單總報酬率不顯示
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 50000.0, "net_investment": 100000.0},
                {"year_month": "2026-02", "market_value": 0.0, "net_investment": -100000.0},
            ]
        )
        pnl, simple_return = ReturnService().compute_pnl(monthly=monthly, initial_cost=0.0)
        assert simple_return is None

    @pytest.mark.scenario("SC-023")
    def test_sc023_insurance_surrender_value_below_premium_is_negative(self):
        # 保險：已繳保費 300000 為初始成本、解約金 250000 為市值、無額外淨投入
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 250000.0, "net_investment": 0.0},
            ]
        )
        pnl, simple_return = ReturnService().compute_pnl(monthly=monthly, initial_cost=300000.0)
        # 賺賠 250000−300000=−50000；簡單報酬 −50000÷300000 = −16.67%
        assert pnl == pytest.approx(-50000.0)
        assert _approx(simple_return, -50000.0 / 300000.0)

    @pytest.mark.scenario("SC-023")
    def test_sc023_surrender_value_carry_forward_when_blank(self):
        # 保險當月未取得解約金（留空）：沿用上一有值月份作為市值參與賺賠
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 250000.0, "net_investment": 0.0},
                {"year_month": "2026-02", "market_value": None, "net_investment": 0.0},
            ]
        )
        pnl, simple_return = ReturnService().compute_pnl(monthly=monthly, initial_cost=300000.0)
        assert pnl == pytest.approx(-50000.0)


class TestInitialCostMarketValueIsolation:
    """compute_twr 與 compute_pnl 對 initial_cost / initial_market_value 的強制隔離。"""

    @pytest.mark.scenario("SC-018")
    def test_sc018_twr_uses_market_value_not_recorded_before_gain(self):
        # 舊持倉：初始市值 500000、初始成本 300000（記錄前 200000 價差）
        # 持有期間市值不變、無資金流動 → TWR 應為 0%，不把 200000 算成第一期報酬
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 500000.0, "net_investment": 0.0},
            ]
        )
        twr = ReturnService().compute_twr(monthly=monthly, initial_market_value=500000.0)
        assert _approx(twr, 0.0)

    @pytest.mark.scenario("SC-018")
    def test_sc018_pnl_includes_recorded_before_gain_via_cost(self):
        # 賺賠以初始成本 300000 起算 → 含記錄前 200000 價差
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 500000.0, "net_investment": 0.0},
            ]
        )
        pnl, simple_return = ReturnService().compute_pnl(monthly=monthly, initial_cost=300000.0)
        assert pnl == pytest.approx(200000.0)
        assert _approx(simple_return, 200000.0 / 300000.0)

    @pytest.mark.scenario("SC-018")
    def test_sc018_compute_twr_signature_rejects_initial_cost(self):
        # 介面護欄：compute_twr 不接受 initial_cost，從簽名杜絕混用
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 500000.0, "net_investment": 0.0},
            ]
        )
        with pytest.raises(TypeError):
            ReturnService().compute_twr(  # type: ignore[call-arg]
                monthly=monthly, initial_market_value=500000.0, initial_cost=300000.0
            )

    @pytest.mark.scenario("SC-018")
    def test_sc018_compute_pnl_signature_rejects_initial_market_value(self):
        # 介面護欄：compute_pnl 不接受 initial_market_value
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 500000.0, "net_investment": 0.0},
            ]
        )
        with pytest.raises(TypeError):
            ReturnService().compute_pnl(  # type: ignore[call-arg]
                monthly=monthly, initial_cost=300000.0, initial_market_value=500000.0
            )

    @pytest.mark.scenario("SC-018")
    def test_sc018_equal_cost_and_market_value_align_pnl_and_twr_base(self):
        # 新買進：初始市值＝初始成本 500000，TWR 與賺賠起點一致
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 550000.0, "net_investment": 0.0},
            ]
        )
        service = ReturnService()
        twr = service.compute_twr(monthly=monthly, initial_market_value=500000.0)
        pnl, simple_return = service.compute_pnl(monthly=monthly, initial_cost=500000.0)
        # 起點一致時 TWR 與簡單報酬率皆 = 10%
        assert _approx(twr, 0.10)
        assert _approx(simple_return, 0.10)
