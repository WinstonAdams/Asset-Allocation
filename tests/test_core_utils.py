# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.core.utils import adjacent_periods, parse_year_month, year_month_add


class TestParseYearMonth:
    """parse_year_month：將 'YYYY-MM' 解析為 (year, month)。"""

    def test_parses_standard_year_month(self):
        assert parse_year_month("2026-06") == (2026, 6)

    def test_parses_january_boundary(self):
        assert parse_year_month("2026-01") == (2026, 1)

    def test_parses_december_boundary(self):
        assert parse_year_month("2026-12") == (2026, 12)

    @pytest.mark.parametrize(
        "bad",
        [
            "",  # 空字串
            "2026/06",  # 分隔符錯誤
            "2026-6",  # 月份未補零
            "2026-13",  # 月份超出範圍
            "2026-00",  # 月份為 0
            "abc",  # 非日期字串
            "2026",  # 缺月份
        ],
    )
    def test_rejects_malformed_input(self, bad):
        # 格式不合的年月一律視為資料錯誤
        with pytest.raises(DataValidationError):
            parse_year_month(bad)


class TestYearMonthAdd:
    """year_month_add：對 'YYYY-MM' 做月份加減，回傳 'YYYY-MM'。"""

    def test_adds_one_month(self):
        assert year_month_add("2026-06", 1) == "2026-07"

    def test_subtracts_one_month(self):
        assert year_month_add("2026-06", -1) == "2026-05"

    def test_zero_offset_returns_same_month(self):
        assert year_month_add("2026-06", 0) == "2026-06"

    def test_rolls_over_year_forward(self):
        assert year_month_add("2026-12", 1) == "2027-01"

    def test_rolls_over_year_backward(self):
        assert year_month_add("2026-01", -1) == "2025-12"

    def test_large_forward_jump_crosses_year(self):
        assert year_month_add("2026-06", 12) == "2027-06"

    def test_large_backward_jump_crosses_multiple_years(self):
        assert year_month_add("2026-06", -18) == "2024-12"

    def test_rejects_malformed_input(self):
        with pytest.raises(DataValidationError):
            year_month_add("2026-13", 1)


class TestAdjacentPeriods:
    """adjacent_periods：從有資料的月份序列抽出相鄰期間段（缺月跳過、不補插）。"""

    def test_consecutive_months_form_adjacent_segments(self):
        assert adjacent_periods(["2026-01", "2026-02", "2026-03"]) == [
            ("2026-01", "2026-02"),
            ("2026-02", "2026-03"),
        ]

    def test_gap_month_is_skipped_not_filled(self):
        # 缺 2026-03：相鄰有資料月 2026-02 與 2026-04 直接成一段，不補插 2026-03
        assert adjacent_periods(["2026-01", "2026-02", "2026-04"]) == [
            ("2026-01", "2026-02"),
            ("2026-02", "2026-04"),
        ]

    def test_single_month_has_no_period(self):
        assert adjacent_periods(["2026-01"]) == []

    def test_empty_sequence_has_no_period(self):
        assert adjacent_periods([]) == []

    def test_unsorted_input_is_ordered_chronologically(self):
        assert adjacent_periods(["2026-03", "2026-01", "2026-02"]) == [
            ("2026-01", "2026-02"),
            ("2026-02", "2026-03"),
        ]

    def test_duplicate_months_are_collapsed(self):
        # 同一有資料月重複出現只視為一個節點
        assert adjacent_periods(["2026-01", "2026-01", "2026-02"]) == [
            ("2026-01", "2026-02"),
        ]

    def test_year_boundary_segment(self):
        assert adjacent_periods(["2026-12", "2027-01"]) == [
            ("2026-12", "2027-01"),
        ]
