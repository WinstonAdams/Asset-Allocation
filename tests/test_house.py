"""買房 bucket 口徑、進度與組成警示：純運算測試（SC-062~065）。

HouseService.bucket_value/bucket_progress/bucket_composition_warning 皆為純函式，
直接餵虛構的 HoldingModel/MonthlyRecordModel/HouseParams 驗證，不連任何 DB。
所有金額、年份皆為虛構值，不含任何個人化真實數字。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_PURPOSE
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParams
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.services.house_service import HouseService


def _holding(
    holding_id: int,
    name: str,
    category: str,
    *,
    purpose: str = HOLDING_PURPOSE.GENERAL,
    initial_market_value: float = 0.0,
) -> HoldingModel:
    """建立一個資產項目主檔（供 bucket 系列測試共用）。"""
    return HoldingModel(
        holding_id=holding_id,
        name=name,
        kind="asset",
        category=category,
        initial_market_value=initial_market_value,
        initial_cost=initial_market_value,
        purpose=purpose,
    )


def _record(
    holding_id: int, year_month: str, market_value: float | None
) -> MonthlyRecordModel:
    return MonthlyRecordModel(
        holding_id=holding_id, year_month=year_month, market_value=market_value
    )


def _params(**overrides) -> HouseParams:
    """全數採虛構中性值的完整買房參數，供各測試以 kwargs 覆寫單一欄位。"""
    base = {
        "target_total_price": 0.0,
        "target_year": 0,
        "monthly_after_tax_income": 0.0,
        "income_threshold": 0.0,
        "cash_floor": 0.0,
        "down_payment_ratio": 33.0,
        "payment_cap_ratio": 35.0,
        "test_annual_rate": 2.5,
        "loan_years": 30,
    }
    base.update(overrides)
    return HouseParams(**base)


def _approx(value: float | None, expected: float, abs_: float = 1e-6) -> bool:
    return value is not None and value == pytest.approx(expected, abs=abs_)


@pytest.fixture
def service() -> HouseService:
    return HouseService()


class TestBucketValueSumsHouseHoldings:
    """bucket_value：僅計購屋標記項目的最新月度市值合計（SC-062）。"""

    @pytest.mark.scenario("SC-062")
    def test_sc062_sums_house_marked_holdings_only(self, service):
        holdings = [
            _holding(1, "範例定存", ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
            _holding(2, "範例股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.HOUSE),
            _holding(
                3, "範例活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.GENERAL
            ),
        ]
        month_records = [
            _record(1, "2026-06", 600_000.0),
            _record(2, "2026-06", 400_000.0),
            _record(3, "2026-06", 500_000.0),
        ]

        bucket = service.bucket_value(month_records=month_records, holdings=holdings)

        assert _approx(bucket, 1_000_000.0)

    @pytest.mark.scenario("SC-062")
    def test_sc062_house_holding_without_any_monthly_record_uses_initial_market_value(
        self, service
    ):
        holdings = [
            _holding(1, "範例定存", ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
            _holding(2, "範例股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.HOUSE),
            _holding(
                3, "範例活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.GENERAL
            ),
            _holding(
                4,
                "範例新定存",
                ASSET_CATEGORIES.TIME_DEPOSIT,
                purpose=HOLDING_PURPOSE.HOUSE,
                initial_market_value=200_000.0,
            ),
        ]
        month_records = [
            _record(1, "2026-06", 600_000.0),
            _record(2, "2026-06", 400_000.0),
            _record(3, "2026-06", 500_000.0),
            # holding_id=4（範例新定存）尚無任何月度紀錄
        ]

        bucket = service.bucket_value(month_records=month_records, holdings=holdings)

        assert _approx(bucket, 1_200_000.0)

    @pytest.mark.scenario("SC-062")
    def test_sc062_no_house_marked_holding_bucket_is_zero(self, service):
        holdings = [
            _holding(
                1, "範例活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.GENERAL
            ),
        ]
        month_records = [_record(1, "2026-06", 500_000.0)]

        bucket = service.bucket_value(month_records=month_records, holdings=holdings)

        assert bucket == 0.0

    @pytest.mark.scenario("SC-062")
    def test_sc062_house_holding_empty_input_bucket_is_zero(self, service):
        assert service.bucket_value(month_records=[], holdings=[]) == 0.0

    @pytest.mark.scenario("SC-062")
    def test_sc062_house_holding_zero_value_in_latest_month_counts_as_zero_not_initial(
        self, service
    ):
        # 最新月快照市值恰為 0：以 0 計，不回退初始市值（初始市值僅用於「無任何月度紀錄」）
        holdings = [
            _holding(
                1,
                "範例股票",
                ASSET_CATEGORIES.TW_STOCK,
                purpose=HOLDING_PURPOSE.HOUSE,
                initial_market_value=300_000.0,
            ),
        ]
        month_records = [_record(1, "2026-06", 0.0)]

        bucket = service.bucket_value(month_records=month_records, holdings=holdings)

        assert bucket == 0.0

    @pytest.mark.scenario("SC-062")
    def test_sc062_house_holding_sold_before_latest_month_not_fallback_to_initial(
        self, service
    ):
        # 曾有紀錄（早於最新月）但最新月缺列＝已出清不再持有：計 0，非回退初始市值
        holdings = [
            _holding(
                1,
                "範例股票",
                ASSET_CATEGORIES.TW_STOCK,
                purpose=HOLDING_PURPOSE.HOUSE,
                initial_market_value=300_000.0,
            ),
            _holding(
                2, "範例定存", ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE
            ),
        ]
        month_records = [
            _record(1, "2026-05", 0.0),  # 5 月出清（賣出當月記市值 0）
            _record(2, "2026-06", 700_000.0),  # 最新月僅剩此項目
        ]

        bucket = service.bucket_value(month_records=month_records, holdings=holdings)

        assert bucket == 700_000.0

    @pytest.mark.scenario("SC-062")
    def test_sc062_house_holding_blank_market_value_in_latest_month_contributes_zero(
        self, service
    ):
        # 最新月市值留空（仍持有未更新）：既有慣例（AllocationService 同口徑）不貢獻市值
        holdings = [
            _holding(1, "範例股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.HOUSE),
        ]
        month_records = [_record(1, "2026-06", None)]

        bucket = service.bucket_value(month_records=month_records, holdings=holdings)

        assert bucket == 0.0


class TestBucketProgress:
    """bucket_progress：目標金額、缺口、進度百分比與每年需累積速率（SC-063/SC-064）。"""

    @pytest.mark.scenario("SC-063")
    def test_sc063_target_amount_gap_progress_and_annual_rate(self, service):
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=2028)

        progress = service.bucket_progress(
            bucket_value=1_000_000.0, params=params, current_year=2026
        )

        assert _approx(progress.target_amount, 1_500_000.0)
        assert _approx(progress.gap, 500_000.0)
        assert _approx(progress.progress_pct, 66.6666667, abs_=1e-4)
        assert progress.years_to_target == 2
        assert progress.reached_target_year is False
        assert _approx(progress.required_annual_accumulation, 250_000.0)

    @pytest.mark.scenario("SC-063")
    def test_sc063_bucket_over_target_gap_zero_progress_not_capped_at_100(self, service):
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=2028)

        progress = service.bucket_progress(
            bucket_value=1_600_000.0, params=params, current_year=2026
        )

        assert progress.gap == 0.0
        assert _approx(progress.progress_pct, 106.6666667, abs_=1e-4)

    @pytest.mark.scenario("SC-063")
    def test_sc063_one_year_remaining_annual_accumulation_equals_full_gap(self, service):
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=2027)

        progress = service.bucket_progress(
            bucket_value=1_000_000.0, params=params, current_year=2026
        )

        assert progress.years_to_target == 1
        assert _approx(progress.required_annual_accumulation, progress.gap)

    @pytest.mark.scenario("SC-063")
    def test_sc063_progress_pct_exactly_100_when_bucket_equals_target(self, service):
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=2028)

        progress = service.bucket_progress(
            bucket_value=1_500_000.0, params=params, current_year=2026
        )

        assert _approx(progress.progress_pct, 100.0)


class TestBucketProgressTargetYearBoundaries:
    """目標年已到、已過或未設定時，速率不除以零（SC-064）。"""

    @pytest.mark.scenario("SC-064")
    def test_sc064_target_year_is_current_year_shows_reached_not_rate(self, service):
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=2026)

        progress = service.bucket_progress(
            bucket_value=1_000_000.0, params=params, current_year=2026
        )

        assert progress.years_to_target == 0
        assert progress.reached_target_year is True
        assert progress.required_annual_accumulation is None

    @pytest.mark.scenario("SC-064")
    def test_sc064_target_year_already_passed_shows_reached_not_rate(self, service):
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=2025)

        progress = service.bucket_progress(
            bucket_value=1_000_000.0, params=params, current_year=2026
        )

        assert progress.years_to_target == -1
        assert progress.reached_target_year is True
        assert progress.required_annual_accumulation is None

    @pytest.mark.scenario("SC-064")
    def test_sc064_target_year_unset_neither_rate_nor_reached_shown(self, service):
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=0)

        progress = service.bucket_progress(
            bucket_value=1_000_000.0, params=params, current_year=2026
        )

        assert progress.years_to_target is None
        assert progress.reached_target_year is False
        assert progress.required_annual_accumulation is None

    @pytest.mark.scenario("SC-064")
    def test_sc064_no_zero_division_error_when_target_year_equals_current_year(self, service):
        # 目標年即當年（速率分母本應為 0）：不得拋出例外
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, target_year=2026)
        service.bucket_progress(bucket_value=1_000_000.0, params=params, current_year=2026)


class TestBucketCompositionWarning:
    """bucket 含非活存/定存資產時序列風險提示，距目標年≤5年強化（SC-065）。"""

    @pytest.mark.scenario("SC-065")
    def test_sc065_non_cash_asset_shows_general_warning_when_more_than_5_years_left(
        self, service
    ):
        house_holdings = [
            _holding(1, "範例定存", ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
            _holding(2, "範例股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.HOUSE),
        ]
        month_records = [
            _record(1, "2026-06", 600_000.0),
            _record(2, "2026-06", 400_000.0),
        ]

        warning = service.bucket_composition_warning(
            house_holdings=house_holdings, month_records=month_records, years_to_target=8
        )

        assert warning.has_non_cash is True
        assert _approx(warning.non_cash_value, 400_000.0)
        assert warning.intensified is False

    @pytest.mark.scenario("SC-065")
    @pytest.mark.parametrize(
        ("years_to_target", "expected_intensified"),
        [(5, True), (6, False)],
    )
    def test_sc065_five_years_boundary_intensifies_at_exactly_5(
        self, service, years_to_target, expected_intensified
    ):
        house_holdings = [
            _holding(1, "範例股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.HOUSE),
        ]
        month_records = [_record(1, "2026-06", 400_000.0)]

        warning = service.bucket_composition_warning(
            house_holdings=house_holdings,
            month_records=month_records,
            years_to_target=years_to_target,
        )

        assert warning.intensified is expected_intensified

    @pytest.mark.scenario("SC-065")
    @pytest.mark.parametrize("years_to_target", [0, -1])
    def test_sc065_target_year_reached_or_passed_intensifies(self, service, years_to_target):
        house_holdings = [
            _holding(1, "範例股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.HOUSE),
        ]
        month_records = [_record(1, "2026-06", 400_000.0)]

        warning = service.bucket_composition_warning(
            house_holdings=house_holdings,
            month_records=month_records,
            years_to_target=years_to_target,
        )

        assert warning.intensified is True

    @pytest.mark.scenario("SC-065")
    def test_sc065_all_cash_categories_no_warning(self, service):
        house_holdings = [
            _holding(1, "範例定存", ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE),
            _holding(
                2, "範例活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE
            ),
        ]
        month_records = [
            _record(1, "2026-06", 600_000.0),
            _record(2, "2026-06", 400_000.0),
        ]

        warning = service.bucket_composition_warning(
            house_holdings=house_holdings, month_records=month_records, years_to_target=8
        )

        assert warning.has_non_cash is False
        assert warning.non_cash_value == 0.0

    @pytest.mark.scenario("SC-065")
    def test_sc065_target_year_unset_never_intensifies(self, service):
        house_holdings = [
            _holding(1, "範例股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.HOUSE),
        ]
        month_records = [_record(1, "2026-06", 400_000.0)]

        warning = service.bucket_composition_warning(
            house_holdings=house_holdings, month_records=month_records, years_to_target=None
        )

        assert warning.has_non_cash is True
        assert warning.intensified is False
