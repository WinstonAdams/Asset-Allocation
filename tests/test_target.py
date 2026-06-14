# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, DEFAULT_REBALANCE_THRESHOLD
from asset_lab.models.results import AllocationSnapshot
from asset_lab.models.target import TargetAllocationModel
from asset_lab.services.allocation_service import AllocationService


def _snapshot(category: str, weight: float, *, year_month: str = "2026-05") -> AllocationSnapshot:
    """以分類粒度建立一筆現況佔比（%）；市值對偏離判定無影響故給佔位值。"""
    return AllocationSnapshot(
        year_month=year_month, dimension_key=category, market_value=weight, weight=weight
    )


def _target(category: str, weight: float) -> TargetAllocationModel:
    """以分類與目標比重（%）建立一筆目標配置。"""
    return TargetAllocationModel(category=category, target_weight=weight)


def _by_category(rows):
    """將 DriftRow 清單轉為 {分類: DriftRow} 便於斷言。"""
    return {row.category: row for row in rows}


class TestComputeDrift:
    """compute_drift：現況佔比對目標比重的偏離（百分點）—— SC-029。"""

    @pytest.mark.scenario("SC-029")
    def test_sc029_drift_is_current_minus_target_in_percentage_points(self):
        # 目標台股60/現金40，現況台股68/現金32：偏離 = 現況% − 目標% → +8、−8
        snapshot = [
            _snapshot(ASSET_CATEGORIES.TW_STOCK, 68.0),
            _snapshot(ASSET_CATEGORIES.CASH, 32.0),
        ]
        targets = [
            _target(ASSET_CATEGORIES.TW_STOCK, 60.0),
            _target(ASSET_CATEGORIES.CASH, 40.0),
        ]
        rows = AllocationService().compute_drift(
            snapshot=snapshot, targets=targets, threshold=DEFAULT_REBALANCE_THRESHOLD
        )
        by_category = _by_category(rows)
        assert by_category[ASSET_CATEGORIES.TW_STOCK].drift == pytest.approx(8.0)
        assert by_category[ASSET_CATEGORIES.CASH].drift == pytest.approx(-8.0)

    @pytest.mark.scenario("SC-029")
    def test_sc029_carries_current_and_target_weights_as_percent(self):
        # 偏離列同時攜帶現況%與目標%（皆 0–100），供 UI 並列呈現
        snapshot = [_snapshot(ASSET_CATEGORIES.TW_STOCK, 68.0)]
        targets = [_target(ASSET_CATEGORIES.TW_STOCK, 60.0)]
        row = AllocationService().compute_drift(
            snapshot=snapshot, targets=targets, threshold=DEFAULT_REBALANCE_THRESHOLD
        )[0]
        assert row.current_weight == pytest.approx(68.0)
        assert row.target_weight == pytest.approx(60.0)

    @pytest.mark.scenario("SC-029")
    def test_sc029_category_with_target_but_no_current_holdings_drifts_negative(self):
        # 設了現金40%目標但當月無現金持有：現況%視為 0，偏離 = 0 − 40 = −40
        snapshot = [_snapshot(ASSET_CATEGORIES.TW_STOCK, 100.0)]
        targets = [
            _target(ASSET_CATEGORIES.TW_STOCK, 60.0),
            _target(ASSET_CATEGORIES.CASH, 40.0),
        ]
        by_category = _by_category(
            AllocationService().compute_drift(
                snapshot=snapshot, targets=targets, threshold=DEFAULT_REBALANCE_THRESHOLD
            )
        )
        assert by_category[ASSET_CATEGORIES.CASH].current_weight == pytest.approx(0.0)
        assert by_category[ASSET_CATEGORIES.CASH].drift == pytest.approx(-40.0)


class TestRebalanceFlag:
    """needs_rebalance：偏離絕對值嚴格超過門檻才標示再平衡 —— SC-030。"""

    @pytest.mark.scenario("SC-030")
    def test_sc030_abs_drift_above_threshold_flags_rebalance(self):
        # 偏離 +8、門檻 5：|8| > 5 → 標示需再平衡
        snapshot = [_snapshot(ASSET_CATEGORIES.TW_STOCK, 68.0)]
        targets = [_target(ASSET_CATEGORIES.TW_STOCK, 60.0)]
        row = AllocationService().compute_drift(
            snapshot=snapshot, targets=targets, threshold=5.0
        )[0]
        assert row.needs_rebalance is True

    @pytest.mark.scenario("SC-030")
    def test_sc030_abs_drift_below_threshold_not_flagged(self):
        # 偏離 +3、門檻 5：|3| ≤ 5 → 不標示再平衡
        snapshot = [_snapshot(ASSET_CATEGORIES.TW_STOCK, 63.0)]
        targets = [_target(ASSET_CATEGORIES.TW_STOCK, 60.0)]
        row = AllocationService().compute_drift(
            snapshot=snapshot, targets=targets, threshold=5.0
        )[0]
        assert row.needs_rebalance is False

    @pytest.mark.scenario("SC-030")
    def test_sc030_abs_drift_equal_to_threshold_not_flagged(self):
        # 偏離絕對值剛好等於門檻（5 = 5）：不標示再平衡（嚴格大於才標示）
        snapshot = [_snapshot(ASSET_CATEGORIES.TW_STOCK, 65.0)]
        targets = [_target(ASSET_CATEGORIES.TW_STOCK, 60.0)]
        row = AllocationService().compute_drift(
            snapshot=snapshot, targets=targets, threshold=5.0
        )[0]
        assert row.drift == pytest.approx(5.0)
        assert row.needs_rebalance is False

    @pytest.mark.scenario("SC-030")
    def test_sc030_negative_drift_uses_absolute_value(self):
        # 偏離 −8（現況低於目標）、門檻 5：取絕對值 |−8| > 5 → 標示需再平衡
        snapshot = [_snapshot(ASSET_CATEGORIES.CASH, 32.0)]
        targets = [_target(ASSET_CATEGORIES.CASH, 40.0)]
        row = AllocationService().compute_drift(
            snapshot=snapshot, targets=targets, threshold=5.0
        )[0]
        assert row.drift == pytest.approx(-8.0)
        assert row.needs_rebalance is True

    @pytest.mark.scenario("SC-030")
    def test_sc030_category_without_target_is_not_judged(self):
        # 保險有現況佔比但未設目標：不顯示偏離、不判定再平衡（不出現在結果）
        snapshot = [
            _snapshot(ASSET_CATEGORIES.TW_STOCK, 70.0),
            _snapshot(ASSET_CATEGORIES.INSURANCE, 30.0),
        ]
        targets = [_target(ASSET_CATEGORIES.TW_STOCK, 60.0)]
        rows = AllocationService().compute_drift(
            snapshot=snapshot, targets=targets, threshold=5.0
        )
        categories = {row.category for row in rows}
        assert categories == {ASSET_CATEGORIES.TW_STOCK}

    @pytest.mark.scenario("SC-030")
    def test_sc030_no_targets_yields_empty_result(self):
        # 完全未設任何目標比重：無任何分類可判定偏離 → 空清單
        snapshot = [_snapshot(ASSET_CATEGORIES.TW_STOCK, 100.0)]
        rows = AllocationService().compute_drift(
            snapshot=snapshot, targets=[], threshold=5.0
        )
        assert rows == []
