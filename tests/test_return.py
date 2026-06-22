# ==== 原生（標準庫） ====
from datetime import date

# ==== 第三方套件 ====
import pandas as pd
import pytest

# ==== 專案內部 ====
from asset_lab.models.holding import HoldingModel
from asset_lab.services.return_service import ReturnService


def _range_df(rows: list[dict]) -> pd.DataFrame:
    """以 (holding_id, year_month, market_value, net_investment) 列組成區間 DataFrame。

    Args:
        rows: 每列含 holding_id、year_month、market_value、net_investment 鍵的 dict。

    Returns:
        欄位齊全的區間 DataFrame，供三維度彙總使用。
    """
    return pd.DataFrame(
        rows, columns=["holding_id", "year_month", "market_value", "net_investment"]
    )


def _asset(
    holding_id: int, category: str, initial_market_value: float, initial_cost: float | None = None
) -> HoldingModel:
    """建立一個資產項目主檔。未指定初始成本時與初始市值一致（對齊 TWR 與簡單報酬起點）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=f"資產{holding_id}",
        kind="asset",
        category=category,
        initial_market_value=initial_market_value,
        initial_cost=initial_market_value if initial_cost is None else initial_cost,
    )


def _result_by(results, dimension_key):
    """從結果清單取出指定維度鍵的單一 ReturnResult。"""
    matched = [r for r in results if r.dimension_key == dimension_key]
    assert len(matched) == 1
    return matched[0]


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


class TestComputeMwr:
    """compute_mwr：以 XIRR 求解現金流年化報酬，不收斂時降級回 (None, 'not_converged')。"""

    @pytest.mark.scenario("SC-015")
    def test_sc015_xirr_annualizes_pure_growth_over_one_year(self):
        # 初始市值 100000（流出），整整持有 12 個月、無中途資金流動，末月市值 110000（流入）
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-02", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-03", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-04", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-05", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-06", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-07", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-08", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-09", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-10", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-11", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-12", "market_value": 110000.0, "net_investment": 0.0},
            ]
        )
        mwr, status = ReturnService().compute_mwr(monthly=monthly, initial_market_value=100000.0)
        # 初始投入 100000 滿一年後變 110000 → 年化內部報酬率 10%
        assert status == "ok"
        assert _approx(mwr, 0.10)

    @pytest.mark.scenario("SC-015")
    def test_sc015_mid_investment_is_negative_cash_flow(self):
        # 中途投入計為負現金流（流出）：初始 100000，2026-07 投入 50000，末月市值 165000
        monthly = _monthly(
            [
                {"year_month": "2026-07", "market_value": None, "net_investment": 50000.0},
                {"year_month": "2027-01", "market_value": 165000.0, "net_investment": 0.0},
            ]
        )
        mwr, status = ReturnService().compute_mwr(monthly=monthly, initial_market_value=100000.0)
        # 投入為負現金流、終值為正現金流 → 求得正的年化內部報酬率
        assert status == "ok"
        assert mwr is not None and mwr > 0.0

    @pytest.mark.scenario("SC-015")
    def test_sc015_withdrawal_is_positive_cash_flow(self):
        # 中途提領計為正現金流（流入）：初始 100000，2026-07 提領 20000，末月市值 90000
        monthly = _monthly(
            [
                {"year_month": "2026-07", "market_value": None, "net_investment": -20000.0},
                {"year_month": "2027-01", "market_value": 90000.0, "net_investment": 0.0},
            ]
        )
        mwr, status = ReturnService().compute_mwr(monthly=monthly, initial_market_value=100000.0)
        # 提領（+20000）與終值（+90000）合計回收 110000，對應正報酬
        assert status == "ok"
        assert mwr is not None and mwr > 0.0

    @pytest.mark.scenario("SC-015")
    def test_sc015_terminal_value_blank_carries_forward(self):
        # 末月市值留空（仍持有未更新）：沿用上一有值月份作為終值現金流
        monthly = _monthly(
            [
                {"year_month": "2026-06", "market_value": 130000.0, "net_investment": 0.0},
                {"year_month": "2026-12", "market_value": None, "net_investment": 0.0},
            ]
        )
        mwr, status = ReturnService().compute_mwr(monthly=monthly, initial_market_value=100000.0)
        # 終值沿用 130000 → 仍可求解出正報酬
        assert status == "ok"
        assert mwr is not None and mwr > 0.0

    @pytest.mark.scenario("SC-015")
    def test_sc015_zero_opening_position_built_from_net_investment(self):
        # 期初市值 0、靠當期淨投入建倉：初始現金流為 0，投入與終值仍構成有效現金流
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": None, "net_investment": 100000.0},
                {"year_month": "2027-01", "market_value": 110000.0, "net_investment": 0.0},
            ]
        )
        mwr, status = ReturnService().compute_mwr(monthly=monthly, initial_market_value=0.0)
        # 投入 100000 一年後 110000 → 約 10% 年化
        assert status == "ok"
        assert mwr is not None and mwr > 0.0

    @pytest.mark.scenario("SC-016")
    def test_sc016_no_sign_change_does_not_converge(self):
        # 現金流全為同號（初始流出 + 末月市值為 0、無任何回收）→ XIRR 無正負交替、無法收斂
        monthly = _monthly(
            [
                {"year_month": "2026-06", "market_value": 0.0, "net_investment": 0.0},
            ]
        )
        mwr, status = ReturnService().compute_mwr(monthly=monthly, initial_market_value=100000.0)
        # 無法收斂時降級：mwr 不呈現數值、狀態標記為 not_converged
        assert mwr is None
        assert status == "not_converged"

    @pytest.mark.scenario("SC-016")
    def test_sc016_empty_series_degrades_gracefully(self):
        # 無任何有資料月：只有初始流出、無終值現金流 → 無從求解，降級而非拋出
        mwr, status = ReturnService().compute_mwr(
            monthly=_monthly([]), initial_market_value=100000.0
        )
        assert mwr is None
        assert status == "not_converged"

    @pytest.mark.scenario("SC-016")
    def test_sc016_non_finite_result_is_treated_as_not_converged(self):
        # 求解結果為非有限值（極端現金流導致年化報酬發散為 inf/nan）亦視為不收斂
        # 初始流出趨近於零、單月回收極大值 → 年化內部報酬率發散
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 1e15, "net_investment": 0.0},
            ]
        )
        mwr, status = ReturnService().compute_mwr(monthly=monthly, initial_market_value=1e-12)
        # 非有限求解結果統一降級，不讓 inf 漏到上層當成真實報酬
        assert mwr is None
        assert status == "not_converged"

    @pytest.mark.scenario("SC-016")
    def test_sc016_mwr_failure_does_not_affect_twr_and_pnl(self):
        # 同一序列下 MWR 不收斂，但 TWR 與賺賠/簡單報酬率照常計算，互不拖累
        monthly = _monthly(
            [
                {"year_month": "2026-06", "market_value": 0.0, "net_investment": 0.0},
            ]
        )
        service = ReturnService()
        mwr, mwr_status = service.compute_mwr(monthly=monthly, initial_market_value=100000.0)
        twr = service.compute_twr(monthly=monthly, initial_market_value=100000.0)
        pnl, simple_return = service.compute_pnl(monthly=monthly, initial_cost=100000.0)
        # MWR 降級
        assert mwr is None and mwr_status == "not_converged"
        # TWR 照常：(0 − 0 − 100000) ÷ 100000 = −100%（全額虧損）
        assert _approx(twr, -1.0)
        # 賺賠照常：市值 0 − 累積成本 100000 = −100000
        assert pnl == pytest.approx(-100000.0)
        assert _approx(simple_return, -1.0)

    @pytest.mark.scenario("SC-016")
    def test_sc016_does_not_raise_on_non_converging_input(self):
        # 降級語意保證：不收斂時 compute_mwr 不得讓例外往上拋（否則會拖垮整頁）
        monthly = _monthly(
            [
                {"year_month": "2026-06", "market_value": 0.0, "net_investment": 0.0},
            ]
        )
        # 不應拋出任何例外
        ReturnService().compute_mwr(monthly=monthly, initial_market_value=100000.0)


class TestComputeMwrGapMonths:
    """SC-022：缺月以相鄰有資料月為現金流節點，缺月跳過、不補插值（XIRR 面向）。"""

    @pytest.mark.scenario("SC-022")
    def test_sc022_mwr_cash_flow_nodes_are_data_months_gap_skipped(self):
        # 2026-03 整月缺漏；現金流節點應只取有資料月（2026-01、2026-02、2026-04），
        # 缺月不另造節點、不補插值。直接檢視 _cash_flows 組出的發生日序列。
        with_gap = _monthly(
            [
                {"year_month": "2026-01", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-02", "market_value": None, "net_investment": 50000.0},
                {"year_month": "2026-04", "market_value": 180000.0, "net_investment": 0.0},
            ]
        )
        dates, amounts = ReturnService._cash_flows(with_gap, 100000.0)
        # 初始流出落在首個有資料月前一月（2025-12），其後為三個有資料月月初；無 2026-03 節點
        assert dates == [
            date(2025, 12, 1),
            date(2026, 1, 1),
            date(2026, 2, 1),
            date(2026, 4, 1),
        ]
        # 對應金額：期初流出 −100000；2026-02 投入 50000 計 −50000；末月併入終值 +180000
        assert amounts == pytest.approx([-100000.0, 0.0, -50000.0, 180000.0])

    @pytest.mark.scenario("SC-022")
    def test_sc022_mwr_gap_month_not_interpolated_into_extra_node(self):
        # 缺月不補插：含缺月（2026-03 缺）的序列，與「真的多記一筆 2026-03 中途投入」的
        # 序列必然得出不同 MWR——證實缺月未被當成插值節點偷偷塞進現金流。
        gap_series = _monthly(
            [
                {"year_month": "2026-01", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-04", "market_value": 150000.0, "net_investment": 0.0},
            ]
        )
        extra_real_node = _monthly(
            [
                {"year_month": "2026-01", "market_value": None, "net_investment": 0.0},
                {"year_month": "2026-03", "market_value": None, "net_investment": 30000.0},
                {"year_month": "2026-04", "market_value": 150000.0, "net_investment": 0.0},
            ]
        )
        service = ReturnService()
        mwr_gap, status_gap = service.compute_mwr(monthly=gap_series, initial_market_value=100000.0)
        mwr_extra, status_extra = service.compute_mwr(
            monthly=extra_real_node, initial_market_value=100000.0
        )
        assert status_gap == "ok" and status_extra == "ok"
        assert mwr_gap != pytest.approx(mwr_extra)


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
    def test_sc018_compute_mwr_signature_rejects_initial_cost(self):
        # 介面護欄：compute_mwr 同樣只吃 initial_market_value，不接受 initial_cost
        monthly = _monthly(
            [
                {"year_month": "2026-01", "market_value": 110000.0, "net_investment": 0.0},
            ]
        )
        with pytest.raises(TypeError):
            ReturnService().compute_mwr(  # type: ignore[call-arg]
                monthly=monthly, initial_market_value=100000.0, initial_cost=300000.0
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


class TestComputeReturnsAnnualization:
    """compute_returns 的年化判定：未滿 12 個月只顯示累積、不年化。"""

    @staticmethod
    def _twelve_contiguous_months(end_ym: str) -> pd.DataFrame:
        # 自 end_ym 往回排滿連續 12 個有資料月，每月小幅成長、無資金流動
        from asset_lab.core.utils import year_month_add

        rows = []
        value = 100000.0
        for offset in range(11, -1, -1):
            value *= 1.01
            rows.append(
                {
                    "holding_id": 1,
                    "year_month": year_month_add(end_ym, -offset),
                    "market_value": round(value, 2),
                    "net_investment": 0.0,
                }
            )
        return _range_df(rows)

    @pytest.mark.scenario("SC-019")
    def test_sc019_six_month_period_not_annualized(self):
        # 區間僅涵蓋 6 個月（2026-01 至 2026-06）：TWR/MWR 只顯示累積、不年化
        rows = []
        value = 100000.0
        for index in range(6):
            value *= 1.02
            rows.append(
                {
                    "holding_id": 1,
                    "year_month": f"2026-0{index + 1}",
                    "market_value": round(value, 2),
                    "net_investment": 0.0,
                }
            )
        results = ReturnService().compute_returns(
            range_df=_range_df(rows),
            holdings=[_asset(1, "台股/台股ETF", 100000.0)],
            dimension="overall",
            start_ym="2026-01",
            end_ym="2026-06",
        )
        assert results[0].annualized is False

    @pytest.mark.scenario("SC-019")
    def test_sc019_eleven_month_period_still_not_annualized(self):
        # 滿 11 個月仍未達年化門檻（2025-07 至 2026-05）：不年化
        results = ReturnService().compute_returns(
            range_df=self._twelve_contiguous_months("2026-05").iloc[1:],
            holdings=[_asset(1, "台股/台股ETF", 100000.0)],
            dimension="overall",
            start_ym="2025-07",
            end_ym="2026-05",
        )
        assert results[0].annualized is False

    @pytest.mark.scenario("SC-019")
    def test_sc019_twelve_month_period_is_annualized(self):
        # 區間涵蓋滿 12 個月（2025-06 至 2026-05）：才年化
        results = ReturnService().compute_returns(
            range_df=self._twelve_contiguous_months("2026-05"),
            holdings=[_asset(1, "台股/台股ETF", 100000.0)],
            dimension="overall",
            start_ym="2025-06",
            end_ym="2026-05",
        )
        assert results[0].annualized is True

    @pytest.mark.scenario("SC-035")
    def test_sc035_twelve_month_span_with_gaps_still_annualized(self):
        # 區間日曆月跨度滿 12 個月即年化，即使缺月使實際有資料月只有三個
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2025-06", "market_value": 100000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2025-12", "market_value": 105000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-05", "market_value": 110000.0,
                 "net_investment": 0.0},
            ]
        )
        results = ReturnService().compute_returns(
            range_df=range_df,
            holdings=[_asset(1, "台股/台股ETF", 100000.0)],
            dimension="overall",
            start_ym="2025-06",
            end_ym="2026-05",
        )
        # 以日曆月跨度（2025-06 至 2026-05 ＝ 12 個月）判定，故年化為 True
        assert results[0].annualized is True


class TestComputeReturnsRangeBoundaries:
    """SC-021 邊界：區間內無資料時不顯示、區間須涵蓋至少一個完整月報酬。

    PeriodService.resolve_period 僅做「模式→起訖月」映射（見 test_period.py），
    不負責「區間內是否有資料」「能否構成完整月報酬」的判定；該兩條邊界落在
    ReturnService 計算層：無有資料月時不產生可顯示的報酬，能否構成連乘段決定是否有值。
    """

    @pytest.mark.scenario("SC-021")
    def test_sc021_empty_range_yields_no_displayable_return(self):
        # 區間內無任何資料：三個指標皆為 None（UI 無數值可顯示），不憑空產生報酬
        empty = _range_df([])
        results = ReturnService().compute_returns(
            range_df=empty,
            holdings=[_asset(1, "台股/台股ETF", 100000.0)],
            dimension="overall",
            start_ym="2026-01",
            end_ym="2026-12",
        )
        result = results[0]
        assert result.twr is None
        assert result.mwr is None
        assert result.simple_return is None
        assert result.pnl_amount is None

    @pytest.mark.scenario("SC-021")
    def test_sc021_empty_range_cumulative_twr_series_is_empty(self):
        # 走勢圖：區間內無資料時無任何節點（不顯示）
        series = ReturnService().cumulative_twr_series(
            range_df=_range_df([]), holdings=[_asset(1, "台股/台股ETF", 100000.0)]
        )
        assert series == []

    @pytest.mark.scenario("SC-021")
    def test_sc021_range_with_one_full_month_return_is_displayable(self):
        # 區間涵蓋至少一個完整月報酬（初始市值 100000 + 一個有資料月 110000 構成一段）：有值
        one_month = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-02", "market_value": 110000.0,
                 "net_investment": 0.0},
            ]
        )
        results = ReturnService().compute_returns(
            range_df=one_month,
            holdings=[_asset(1, "台股/台股ETF", 100000.0)],
            dimension="overall",
            start_ym="2026-01",
            end_ym="2026-02",
        )
        # 構成一個完整月報酬段 100000→110000 = 10%，可顯示
        assert _approx(results[0].twr, 0.10)

    @pytest.mark.scenario("SC-021")
    def test_sc021_building_month_only_has_no_full_month_return(self):
        # 不足一個完整月報酬：期初市值 0 且僅有建倉月一段（無下一段），TWR 無從連乘
        building_only = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-01", "market_value": 100000.0,
                 "net_investment": 100000.0},
            ]
        )
        results = ReturnService().compute_returns(
            range_df=building_only,
            holdings=[_asset(1, "台股/台股ETF", 0.0, initial_cost=0.0)],
            dimension="overall",
            start_ym="2026-01",
            end_ym="2026-01",
        )
        # 僅建倉段、無可連乘的完整月報酬 → TWR 不顯示
        assert results[0].twr is None


class TestComputeReturnsDimensions:
    """compute_returns 三維度彙總：整體 / 各分類 / 各單一標的，僅資產不含負債。"""

    @staticmethod
    def _two_assets_two_categories() -> tuple[pd.DataFrame, list[HoldingModel]]:
        # 兩個資產分屬兩分類，各自跨兩月成長且無資金流動；外加一筆負債（不應納入）
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-01", "market_value": 110000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-02", "market_value": 121000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-01", "market_value": 210000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-02", "market_value": 220500.0,
                 "net_investment": 0.0},
                {"holding_id": 9, "year_month": "2026-01", "market_value": 50000.0,
                 "net_investment": 0.0},
                {"holding_id": 9, "year_month": "2026-02", "market_value": 50000.0,
                 "net_investment": 0.0},
            ]
        )
        holdings = [
            _asset(1, "台股/台股ETF", 100000.0),
            _asset(2, "美股/美股ETF", 200000.0),
            HoldingModel(holding_id=9, name="房貸", kind="liability", category=None,
                         initial_market_value=None, initial_cost=None),
        ]
        return range_df, holdings

    @pytest.mark.scenario("SC-020")
    def test_sc020_holding_dimension_one_result_per_asset(self):
        # 單一標的維度：每個資產項目一筆結果，各自以自身序列計算
        range_df, holdings = self._two_assets_two_categories()
        results = ReturnService().compute_returns(
            range_df=range_df, holdings=holdings, dimension="holding",
            start_ym="2026-01", end_ym="2026-02",
        )
        assert {r.dimension_key for r in results} == {"1", "2"}
        # 項目1：100000→110000→121000 = 1.1×1.1 − 1 = 21%
        assert _approx(_result_by(results, "1").twr, 0.21)
        # 項目2：200000→210000→220500 = 1.05×1.05 − 1 = 10.25%
        assert _approx(_result_by(results, "2").twr, 0.1025)

    @pytest.mark.scenario("SC-020")
    def test_sc020_category_dimension_aggregates_member_holdings(self):
        # 分類維度：每個分類一筆結果，以該分類成員標的的彙總序列計算
        range_df, holdings = self._two_assets_two_categories()
        results = ReturnService().compute_returns(
            range_df=range_df, holdings=holdings, dimension="category",
            start_ym="2026-01", end_ym="2026-02",
        )
        assert {r.dimension_key for r in results} == {"台股/台股ETF", "美股/美股ETF"}
        # 單成員分類的 TWR 等同該成員標的的 TWR
        assert _approx(_result_by(results, "台股/台股ETF").twr, 0.21)
        assert _approx(_result_by(results, "美股/美股ETF").twr, 0.1025)

    @pytest.mark.scenario("SC-020")
    def test_sc020_overall_dimension_aggregates_all_assets(self):
        # 整體維度：單一結果，以全體資產同月市值與淨投入的彙總序列計算
        range_df, holdings = self._two_assets_two_categories()
        results = ReturnService().compute_returns(
            range_df=range_df, holdings=holdings, dimension="overall",
            start_ym="2026-01", end_ym="2026-02",
        )
        assert len(results) == 1
        assert results[0].dimension == "overall"
        assert results[0].dimension_key is None
        # 整體初始市值 300000；月末彙總 320000→341500
        # (320000/300000)×(341500/320000) − 1 = 341500/300000 − 1 = 13.8333%
        assert _approx(results[0].twr, 341500.0 / 300000.0 - 1.0)

    @pytest.mark.scenario("SC-020")
    def test_sc020_liabilities_never_enter_any_dimension(self):
        # 三維度皆僅計資產：負債分類（None）不出現在任何維度結果
        range_df, holdings = self._two_assets_two_categories()
        for dimension in ("overall", "category", "holding"):
            results = ReturnService().compute_returns(
                range_df=range_df, holdings=holdings, dimension=dimension,
                start_ym="2026-01", end_ym="2026-02",
            )
            assert all(r.dimension_key != "9" for r in results)
            assert all(r.dimension_key is None or r.dimension_key != "房貸" for r in results)

    @pytest.mark.scenario("SC-020")
    def test_sc020_each_dimension_carries_own_net_investment_terminal_value(self):
        # 各維度以「自身淨投入序列＋自身期末市值為終值」獨立計 MWR；標的中途投入計入自身現金流
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-01", "market_value": 100000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2027-01", "market_value": 165000.0,
                 "net_investment": 50000.0},
            ]
        )
        results = ReturnService().compute_returns(
            range_df=range_df, holdings=[_asset(1, "台股/台股ETF", 100000.0)],
            dimension="holding", start_ym="2026-01", end_ym="2027-01",
        )
        holding_result = _result_by(results, "1")
        # MWR 可收斂（投入為流出、終值為流入），且 PnL 以初始成本 100000 起算
        assert holding_result.mwr_status == "ok"
        assert holding_result.mwr is not None
        # 累積成本 100000 + 50000 = 150000；賺賠 165000 − 150000 = 15000
        assert holding_result.pnl_amount == pytest.approx(15000.0)

    @pytest.mark.scenario("SC-020")
    def test_sc020_dimension_uses_own_data_months_when_member_changes(self):
        # 單一標的中途新增（2026-02 才建倉）：整體維度仍以各自有資料月彙總，不被缺月干擾
        range_df = _range_df(
            [
                {"holding_id": 1, "year_month": "2026-01", "market_value": 100000.0,
                 "net_investment": 0.0},
                {"holding_id": 1, "year_month": "2026-02", "market_value": 110000.0,
                 "net_investment": 0.0},
                {"holding_id": 2, "year_month": "2026-02", "market_value": 50000.0,
                 "net_investment": 50000.0},
            ]
        )
        holdings = [
            _asset(1, "台股/台股ETF", 100000.0),
            _asset(2, "美股/美股ETF", 0.0, initial_cost=0.0),
        ]
        results = ReturnService().compute_returns(
            range_df=range_df, holdings=holdings, dimension="overall",
            start_ym="2026-01", end_ym="2026-02",
        )
        # 整體 2026-01 市值 100000（僅標的1）、2026-02 市值 160000、當月淨投入 50000
        # 段一 100000→100000(無標的2) ... 段二 (160000 − 50000)/100000 = 1.10 → 整體 TWR 10%
        assert _approx(results[0].twr, 0.10)
