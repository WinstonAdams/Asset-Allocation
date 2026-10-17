# ==== 原生（標準庫） ====
from datetime import date

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.core.utils import (
    current_year_month,
    format_amount,
    parse_amount,
    parse_year_month,
    year_month_add,
)


class TestCurrentYearMonth:
    """current_year_month：將指定日期格式化為所屬 'YYYY-MM'（純函式，注入固定日期）。"""

    def test_formats_mid_month_date(self):
        assert current_year_month(date(2026, 6, 15)) == "2026-06"

    def test_pads_single_digit_month(self):
        assert current_year_month(date(2026, 1, 5)) == "2026-01"

    def test_first_day_of_month_same_result_as_last_day(self):
        # 同月不同日應得到相同年月字串（只取年月，不受日影響）
        assert current_year_month(date(2026, 3, 1)) == current_year_month(date(2026, 3, 31))

    def test_year_end_boundary_stays_in_old_year(self):
        assert current_year_month(date(2025, 12, 31)) == "2025-12"

    def test_year_start_boundary_rolls_into_new_year(self):
        assert current_year_month(date(2026, 1, 1)) == "2026-01"


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


class TestFormatAmount:
    """format_amount：金額數值格式化為整數千分位字串（顯示側，SC-081）。"""

    @pytest.mark.scenario("SC-081")
    def test_sc081_formats_positive_integer_with_thousands_separator(self):
        assert format_amount(1234567) == "1,234,567"

    @pytest.mark.scenario("SC-081")
    def test_sc081_formats_negative_integer_with_thousands_separator(self):
        assert format_amount(-50000) == "-50,000"

    @pytest.mark.scenario("SC-081")
    def test_sc081_rounds_decimal_away_from_zero_before_formatting(self):
        # 對齊解析側的取整例子（1234567.6 → 1234568），確保顯示與存檔口徑一致
        assert format_amount(1234567.6) == "1,234,568"

    @pytest.mark.scenario("SC-081")
    def test_sc081_formats_none_as_empty_string(self):
        # 尚無資料（例如欄位從未填寫）時顯示空白，而非 "0" 或 "None"
        assert format_amount(None) == ""

    @pytest.mark.scenario("SC-081")
    def test_sc081_formats_negative_zero_as_zero(self):
        # -0.4 最接近的整數是 0（未達四捨五入進位門檻），且不應顯示成 "-0"
        assert format_amount(-0.4) == "0"

    @pytest.mark.scenario("SC-081")
    def test_sc081_half_tie_rounds_away_from_zero_for_positive_value(self):
        # 整數與小數的中界值（.5）需遠離零取整，而非標準函式庫常見的四捨六入五成雙
        assert format_amount(2.5) == "3"

    @pytest.mark.scenario("SC-081")
    def test_sc081_half_tie_rounds_away_from_zero_for_negative_value(self):
        assert format_amount(-2.5) == "-3"


class TestParseAmount:
    """parse_amount：金額文字解析為數值，格式不符或留空時拒絕（SC-081/SC-082）。"""

    @pytest.mark.scenario("SC-081")
    def test_sc081_parses_plain_digits_without_separator(self):
        assert parse_amount("1234567", field_label="現值") == 1234567.0

    @pytest.mark.scenario("SC-081")
    def test_sc081_parses_amount_with_standard_thousands_grouping(self):
        assert parse_amount("1,234,567", field_label="現值") == 1234567.0

    @pytest.mark.scenario("SC-081")
    def test_sc081_parses_negative_amount_without_separator(self):
        assert parse_amount("-50000", field_label="淨投入") == -50000.0

    @pytest.mark.scenario("SC-081")
    def test_sc081_parses_negative_amount_with_thousands_grouping(self):
        assert parse_amount("-1,234,567", field_label="淨投入") == -1234567.0

    @pytest.mark.scenario("SC-081")
    def test_sc081_rounds_decimal_input_away_from_zero(self):
        assert parse_amount("1234567.6", field_label="現值") == 1234568.0

    @pytest.mark.scenario("SC-081")
    def test_sc081_parses_fullwidth_digits_and_fullwidth_comma(self):
        # 中文輸入法常見的全形數字／全形逗號，NFKC 正規化後等價於半形輸入
        assert parse_amount("１，２３４", field_label="現值") == 1234.0

    @pytest.mark.scenario("SC-081")
    def test_sc081_strips_surrounding_whitespace(self):
        assert parse_amount(" 1000 ", field_label="現值") == 1000.0

    @pytest.mark.scenario("SC-081")
    def test_sc081_half_tie_rounds_away_from_zero(self):
        assert parse_amount("2.5", field_label="現值") == 3.0
        assert parse_amount("-2.5", field_label="現值") == -3.0

    @pytest.mark.scenario("SC-082")
    def test_sc082_rejects_non_standard_thousands_grouping(self):
        with pytest.raises(DataValidationError):
            parse_amount("1,00,000", field_label="現值")

    @pytest.mark.scenario("SC-082")
    def test_sc082_rejects_non_numeric_text(self):
        with pytest.raises(DataValidationError):
            parse_amount("abc", field_label="現值")

    @pytest.mark.scenario("SC-082")
    def test_sc082_rejects_empty_string(self):
        with pytest.raises(DataValidationError):
            parse_amount("", field_label="已實現收益")

    @pytest.mark.scenario("SC-082")
    def test_sc082_rejects_whitespace_only_string(self):
        # 使用者清空後只留下空白字元，等同於清空（未主動輸入 0）
        with pytest.raises(DataValidationError):
            parse_amount("   ", field_label="已實現收益")

    @pytest.mark.scenario("SC-082")
    def test_sc082_rejects_none_input(self):
        with pytest.raises(DataValidationError):
            parse_amount(None, field_label="已實現收益")

    @pytest.mark.scenario("SC-082")
    def test_sc082_error_message_includes_field_label(self):
        with pytest.raises(DataValidationError, match="已實現收益"):
            parse_amount("abc", field_label="已實現收益")

    @pytest.mark.scenario("SC-082")
    def test_sc082_accepts_explicit_zero_as_valid_input(self):
        # 使用者主動輸入 "0"（例如已實現收益維持系統預設值）視為合法，非清空
        assert parse_amount("0", field_label="已實現收益") == 0.0
