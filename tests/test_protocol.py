# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import PROTOCOL_LEVEL_CODE, PROTOCOL_MIN_DATA_MONTHS
from asset_lab.models.protocol import ProtocolThresholds
from asset_lab.models.results import CumulativeTwrPoint
from asset_lab.services.protocol_service import ProtocolService


def _series(cumulative_twrs: list[float]) -> list[CumulativeTwrPoint]:
    """以累積 TWR 清單組成逐月序列（年月依序遞增，僅測試用）。

    Args:
        cumulative_twrs: 依月份順序排列的累積 TWR（小數，如 0.05 表 +5%）。

    Returns:
        對應的 CumulativeTwrPoint 清單。
    """
    return [
        CumulativeTwrPoint(year_month=f"2026-{index + 1:02d}", cumulative_twr=twr)
        for index, twr in enumerate(cumulative_twrs)
    ]


def _thresholds(l1: float = 10.0, l2: float = 20.0, l3: float = 30.0) -> ProtocolThresholds:
    """組出一組回撤門檻（預設對齊常數 L1/L2/L3 = 10/20/30 的預設值）。"""
    return ProtocolThresholds(l1=l1, l2=l2, l3=l3)


def _approx(value: float | None, expected: float) -> bool:
    """以浮點容差比較回撤/報酬率數值。"""
    return value is not None and value == pytest.approx(expected, abs=1e-6)


class TestAssessDrawdownBasis:
    """assess：回撤基準以累積 TWR 成長指數計算，歷史高點納入起始建倉基準（SC-043）。"""

    @pytest.mark.scenario("SC-043")
    def test_sc043_drawdown_from_growth_index_with_inception_baseline(self):
        # 累積 TWR 依序 +5%、−8%、−22%；指數路徑 1.00/1.05/0.92/0.78，歷史高點 1.05
        series = _series([0.05, -0.08, -0.22])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        # 0.78 / 1.05 − 1 ≈ −25.7%
        assert _approx(status.drawdown, 0.78 / 1.05 - 1)
        assert _approx(status.current_cumulative_twr, -0.22)
        assert status.data_month_count == 3
        assert status.status == "ok"

    @pytest.mark.scenario("SC-043")
    def test_sc043_only_losses_peak_still_anchored_at_inception(self):
        # 只跌不漲：每月累積 TWR 皆為負，歷史高點仍以起始基準 1.0 認定，而非第一個下跌月
        series = _series([-0.06, -0.13, -0.19])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        # 若誤把第一個下跌月（指數 0.94）當高點，回撤僅約 −13.8%——本例須為 −19%
        assert _approx(status.drawdown, -0.19)

    @pytest.mark.scenario("SC-043")
    def test_sc043_new_high_has_zero_drawdown(self):
        # 最新累積 TWR 為序列最大且為正：目前回撤為 0%（最新點即歷史高點）
        series = _series([0.05, 0.02, 0.10])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        assert _approx(status.drawdown, 0.0)
        assert status.level_code == PROTOCOL_LEVEL_CODE.L0

    @pytest.mark.scenario("SC-043")
    def test_sc043_peak_in_middle_of_series(self):
        # 歷史高點出現在序列中段（累積 +20%）之後回落至 +5%：以中段高點量測回撤
        series = _series([0.10, 0.20, 0.05])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        # 1.05 / 1.20 − 1 = −12.5%
        assert _approx(status.drawdown, 1.05 / 1.20 - 1)

    @pytest.mark.scenario("SC-043")
    def test_sc043_extreme_gain_then_crash_still_measures_from_true_peak(self):
        # 極端值：先暴漲至指數 10.0（+900%）再腰斬至 5.0，回撤仍須以暴漲後的真實高點量測
        series = _series([9.0, 4.0])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=2
        )
        # 高點 10.0（1+9.0）；目前 5.0（1+4.0）；5.0 / 10.0 − 1 = −50%
        assert _approx(status.drawdown, -0.5)


class TestAssessLevelMapping:
    """assess：回撤深度對應 L0/L1/L2/L3 四級，達門檻即進入較深一級（SC-044）。"""

    @pytest.mark.parametrize(
        ("depth_percent", "expected_level"),
        [
            (0.0, PROTOCOL_LEVEL_CODE.L0),
            (9.99, PROTOCOL_LEVEL_CODE.L0),
            (10.0, PROTOCOL_LEVEL_CODE.L1),  # 恰為 10% → L1（不是 L0）
            (19.99, PROTOCOL_LEVEL_CODE.L1),
            (20.0, PROTOCOL_LEVEL_CODE.L2),  # 恰為 20% → L2（不是 L1）
            (29.99, PROTOCOL_LEVEL_CODE.L2),
            (30.0, PROTOCOL_LEVEL_CODE.L3),  # 恰為 30% → L3（不是 L2）
            (35.0, PROTOCOL_LEVEL_CODE.L3),
        ],
    )
    @pytest.mark.scenario("SC-044")
    def test_sc044_depth_maps_to_expected_level(self, depth_percent, expected_level):
        # 先以兩個小跌月固定歷史高點於 1.0，末月精確跌到目標深度，
        # 使目前回撤恰等於 depth_percent，藉此驗證四級邊界（含恰等門檻）
        series = _series([-0.01, -0.02, -depth_percent / 100])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        assert status.level_code == expected_level

    @pytest.mark.scenario("SC-044")
    def test_sc044_same_input_yields_same_level_across_calls(self):
        # 純運算服務：同一輸入重複呼叫應得到一致結果（無隱藏狀態）
        series = _series([-0.01, -0.02, -0.20])
        service = ProtocolService()
        first = service.assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        second = service.assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        assert first.level_code == second.level_code == PROTOCOL_LEVEL_CODE.L2
        assert first.drawdown == second.drawdown


class TestAssessInsufficientData:
    """assess：累積 TWR 有效月數不足 3 個月時退回 L0 並回報資料不足，不誤報大跌（SC-045）。"""

    @pytest.mark.scenario("SC-045")
    def test_sc045_no_record_returns_no_data_status(self):
        # 有效月數 = 0（完全無紀錄／尚無任何有效累積 TWR 節點）
        status = ProtocolService().assess(
            series=[], thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        assert status.status == "no_data"
        assert status.level_code == PROTOCOL_LEVEL_CODE.L0
        assert status.drawdown is None
        assert status.current_cumulative_twr is None
        assert status.data_month_count == 0

    @pytest.mark.scenario("SC-045")
    @pytest.mark.parametrize("month_count", [1, 2])
    def test_sc045_below_minimum_months_returns_insufficient_data_despite_huge_drop(
        self, month_count
    ):
        # 有效月數 = 1 或 2：即使單月累積 TWR 暴跌 90%，仍須退回 L0、不觸發任何大跌等級、
        # 不顯示回撤深度數值——證明系統不因少數月雜訊誤報大跌
        series = _series([-0.90] * month_count)
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        assert status.status == "insufficient_data"
        assert status.level_code == PROTOCOL_LEVEL_CODE.L0
        assert status.drawdown is None
        assert status.data_month_count == month_count
        # 累積 TWR 本身（非回撤深度）仍可呈現，供關鍵指標區塊獨立顯示
        assert _approx(status.current_cumulative_twr, -0.90)

    @pytest.mark.scenario("SC-045")
    def test_sc045_at_minimum_months_assesses_by_drawdown_depth(self):
        # 有效月數 = 3：達下限，正式依回撤深度判定 L0–L3，不再視為資料不足
        series = _series([-0.01, -0.02, -0.20])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        assert status.status == "ok"
        assert status.level_code == PROTOCOL_LEVEL_CODE.L2
        assert status.drawdown is not None

    @pytest.mark.scenario("SC-045")
    def test_sc045_min_data_months_is_caller_configurable_not_hardcoded(self):
        # min_data_months 為呼叫端注入的參數、非寫死於 Service 內部：
        # 同樣 3 個有效月，若呼叫端要求至少 4 個月才算充足，仍應退回資料不足
        series = _series([-0.01, -0.02, -0.20])
        status = ProtocolService().assess(
            series=series, thresholds=_thresholds(), min_data_months=4
        )
        assert status.status == "insufficient_data"
        assert status.level_code == PROTOCOL_LEVEL_CODE.L0
