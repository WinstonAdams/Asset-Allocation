# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.core.utils import parse_year_month, year_month_add


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
