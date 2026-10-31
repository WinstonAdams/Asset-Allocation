"""買房 bucket 口徑、進度、組成警示、觸發條件檢核與買房頁呈現測試
（SC-056/062~065/066/067/069/070）。

HouseService 各方法皆為純函式，直接餵虛構的 HoldingModel/MonthlyRecordModel/
HouseParams/SubjectiveTriggerModel/AffordabilityResult 驗證，不連任何 DB。
所有金額、年份皆為虛構值，不含任何個人化真實數字。

檔案末段（SC-066/067）改以 AppTest 直接載入 views/house.py，比照 test_settings_view.py
的替身容器慣例，注入 session_state["container"]（house_service/affordability_service
用真正的純運算實作，僅 Repository 層替身），驗證買房頁編排全鏈路（讀參數/主檔/月度紀錄
→ 算 bucket/可負擔性/觸發檢核 → 渲染）接線正確，並覆蓋頁面級呈現行為：5/5 顯示「可啟動
購屋」、未全數達成時顯示缺口清單（含實際值與門檻值）。
"""

# ==== 原生（標準庫） ====
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# ==== 第三方套件 ====
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    ERROR_DETAILS,
    HOLDING_PURPOSE,
    HOUSE_PARAM_KEY,
    HOUSE_TRIGGER,
)
from asset_lab.core.exceptions import PersistenceError
from asset_lab.error_boundary import UNEXPECTED_ERROR_MESSAGE
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParamModel, HouseParams, SubjectiveTriggerModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import AffordabilityResult
from asset_lab.services.affordability_service import AffordabilityService
from asset_lab.services.house_service import HouseService

APP_DIR = Path(__file__).resolve().parent.parent


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


def _subjective(**checks: bool) -> list[SubjectiveTriggerModel]:
    """建立主觀觸發勾選狀態列表（kwargs 為 trigger_key=checked），供觸發檢核測試共用。"""
    return [
        SubjectiveTriggerModel(trigger_key=key, checked=value) for key, value in checks.items()
    ]


def _forward(income_share_pct: float | None) -> AffordabilityResult:
    """建立一個只關心月付占比的正算結果，供 assess_triggers 的月付條件測試共用。"""
    return AffordabilityResult(direction="forward", income_share_pct=income_share_pct)


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
            holdings=house_holdings, month_records=month_records, years_to_target=8
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
            holdings=house_holdings,
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
            holdings=house_holdings,
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
            holdings=house_holdings, month_records=month_records, years_to_target=8
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
            holdings=house_holdings, month_records=month_records, years_to_target=None
        )

        assert warning.has_non_cash is True
        assert warning.intensified is False


class TestCashReserveValue:
    """cash_reserve_value：未標記購屋且分類為活存/定存的最新月市值合計（SC-069）。"""

    @pytest.mark.scenario("SC-069")
    def test_sc069_sums_general_purpose_cash_categories_only(self, service):
        holdings = [
            _holding(
                1, "範例一般活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.GENERAL
            ),
            _holding(
                2, "範例一般定存", ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.GENERAL
            ),
            _holding(
                3, "範例購屋定存", ASSET_CATEGORIES.TIME_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE
            ),
        ]
        month_records = [
            _record(1, "2026-06", 100_000.0),
            _record(2, "2026-06", 100_000.0),
            _record(3, "2026-06", 900_000.0),  # 購屋標記，即使金額大也不計入預備金
        ]

        reserve = service.cash_reserve_value(month_records=month_records, holdings=holdings)

        assert _approx(reserve, 200_000.0)

    @pytest.mark.scenario("SC-069")
    def test_sc069_general_purpose_non_cash_category_not_counted(self, service):
        holdings = [
            _holding(
                1, "範例一般活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.GENERAL
            ),
            _holding(2, "範例一般股票", ASSET_CATEGORIES.TW_STOCK, purpose=HOLDING_PURPOSE.GENERAL),
        ]
        month_records = [
            _record(1, "2026-06", 200_000.0),
            _record(2, "2026-06", 900_000.0),  # 一般用途但非活存/定存，不計入預備金
        ]

        reserve = service.cash_reserve_value(month_records=month_records, holdings=holdings)

        assert _approx(reserve, 200_000.0)

    @pytest.mark.scenario("SC-069")
    def test_sc069_house_marked_cash_holding_excluded_regardless_of_amount(self, service):
        holdings = [
            _holding(
                1, "範例購屋活存", ASSET_CATEGORIES.DEMAND_DEPOSIT, purpose=HOLDING_PURPOSE.HOUSE
            ),
        ]
        month_records = [_record(1, "2026-06", 5_000_000.0)]

        reserve = service.cash_reserve_value(month_records=month_records, holdings=holdings)

        assert reserve == 0.0

    @pytest.mark.scenario("SC-069")
    def test_sc069_empty_input_reserve_is_zero(self, service):
        assert service.cash_reserve_value(month_records=[], holdings=[]) == 0.0


class TestAssessTriggersUnsetParamsNeutralPosture:
    """個人化參數未設定（0）時觸發條件呈現中性姿態，不因恆真不等式誤判達標（SC-056）。"""

    @pytest.mark.scenario("SC-056")
    def test_sc056_income_threshold_unset_not_met_despite_income_present(self, service):
        # 收入門檻未設定（0）、月收 100,000：不得因 100,000 ≥ 0 誤判達標
        params = _params(income_threshold=0.0, monthly_after_tax_income=100_000.0)

        checklist = service.assess_triggers(
            params=params,
            bucket_value=0.0,
            cash_reserve_value=0.0,
            forward_result=_forward(None),
            subjective=_subjective(anchor=True, cognition=True),
        )

        income = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.INCOME)
        assert income.met is False
        assert income.required is None  # 未設定，非「門檻恰為 0」的具體未達標

    @pytest.mark.scenario("SC-056")
    def test_sc056_met_count_denominator_fixed_at_five(self, service):
        # 兩條未設定（收入門檻、現金地板）＋兩條達成（定錨、月付）→ 2/5，分母不縮減
        params = _params(
            target_total_price=5_000_000.0,
            down_payment_ratio=30.0,
            income_threshold=0.0,
            cash_floor=0.0,
            payment_cap_ratio=40.0,
        )

        checklist = service.assess_triggers(
            params=params,
            bucket_value=2_000_000.0,
            cash_reserve_value=999_999.0,
            forward_result=_forward(35.0),
            subjective=_subjective(anchor=True, cognition=False),
        )

        assert len(checklist.conditions) == 5
        assert checklist.met_count == 2
        assert checklist.all_met is False

    @pytest.mark.scenario("SC-056")
    def test_sc056_subjective_never_persisted_defaults_to_not_met(self, service):
        params = _params()

        checklist = service.assess_triggers(
            params=params,
            bucket_value=0.0,
            cash_reserve_value=0.0,
            forward_result=_forward(None),
            subjective=[],
        )

        anchor = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.ANCHOR)
        cognition = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.COGNITION)
        assert anchor.met is False
        assert cognition.met is False

    @pytest.mark.scenario("SC-056")
    def test_sc056_target_total_price_unset_down_payment_and_payment_not_met(self, service):
        # 目標總價未設定：bucket≥0、占比0%≤上限皆恆真，不得誤判達標
        params = _params(target_total_price=0.0, payment_cap_ratio=40.0, cash_floor=300_000.0)

        checklist = service.assess_triggers(
            params=params,
            bucket_value=999_999_999.0,
            cash_reserve_value=999_999_999.0,
            forward_result=_forward(0.0),
            subjective=_subjective(anchor=True, cognition=True),
        )

        down_payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.DOWN_PAYMENT)
        payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.PAYMENT)
        assert down_payment.met is False
        assert down_payment.required is None
        assert payment.met is False
        assert payment.required is None


class TestBucketProgressUnsetTarget:
    """目標總價未設定（0）時 bucket 進度不呈現百分比、缺口與速率（SC-056）。"""

    @pytest.mark.scenario("SC-056")
    def test_sc056_target_total_price_and_year_unset_nothing_numeric_shown(self, service):
        params = _params(target_total_price=0.0, target_year=0)

        progress = service.bucket_progress(
            bucket_value=500_000.0, params=params, current_year=2026
        )

        assert progress.progress_pct is None
        assert progress.years_to_target is None
        assert progress.required_annual_accumulation is None

    @pytest.mark.scenario("SC-056")
    def test_sc056_target_total_price_unset_progress_pct_not_shown_regardless_of_year(
        self, service
    ):
        params = _params(target_total_price=0.0, target_year=2030)

        progress = service.bucket_progress(
            bucket_value=500_000.0, params=params, current_year=2026
        )

        assert progress.progress_pct is None


class TestAffordableTotalPriceUnsetIncome:
    """家庭稅後月收未設定（0）時反推可負擔總價的呈現（SC-056）。"""

    @pytest.mark.scenario("SC-056")
    def test_sc056_reverse_zero_income_returns_none_not_misleading_zero(self):
        result = AffordabilityService().affordable_total_price(
            monthly_income=0,
            payment_cap_ratio_pct=40,
            test_annual_rate_pct=3,
            loan_years=20,
            down_payment_ratio_pct=20,
        )

        # 月收未設定：不得退化為「可負擔 0 元」的誤導性結論，三個反推欄位皆回傳
        # None（而非拋出例外），呈現層據此顯示中性的未設定姿態
        assert result.affordable_total_price is None
        assert result.loan_ceiling is None
        assert result.monthly_payment_cap is None


class TestAssessTriggersDownPaymentDualThreshold:
    """自備條件為雙門檻：bucket 達標且預備金達標缺一不可（SC-069）。"""

    @pytest.mark.scenario("SC-069")
    def test_sc069_bucket_met_but_cash_reserve_below_floor_not_met(self, service):
        params = _params(
            target_total_price=5_000_000.0, down_payment_ratio=30.0, cash_floor=300_000.0
        )

        checklist = service.assess_triggers(
            params=params,
            bucket_value=1_500_000.0,  # 恰達標
            cash_reserve_value=200_000.0,  # 低於地板
            forward_result=_forward(None),
            subjective=_subjective(anchor=False, cognition=False),
        )

        down_payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.DOWN_PAYMENT)
        assert down_payment.met is False

    @pytest.mark.scenario("SC-069")
    def test_sc069_cash_reserve_met_but_bucket_below_target_not_met(self, service):
        params = _params(
            target_total_price=5_000_000.0, down_payment_ratio=30.0, cash_floor=300_000.0
        )

        checklist = service.assess_triggers(
            params=params,
            bucket_value=1_400_000.0,  # 低於目標
            cash_reserve_value=400_000.0,  # 高於地板
            forward_result=_forward(None),
            subjective=_subjective(anchor=False, cognition=False),
        )

        down_payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.DOWN_PAYMENT)
        assert down_payment.met is False

    @pytest.mark.scenario("SC-069")
    def test_sc069_cash_floor_unset_down_payment_not_met_even_if_reserve_nonnegative(
        self, service
    ):
        # 現金地板未設定（0）：預備金半邊 fail-closed 不視為達成，即使 bucket 極大
        params = _params(target_total_price=5_000_000.0, down_payment_ratio=30.0, cash_floor=0.0)

        checklist = service.assess_triggers(
            params=params,
            bucket_value=9_999_999.0,
            cash_reserve_value=0.0,
            forward_result=_forward(None),
            subjective=_subjective(anchor=False, cognition=False),
        )

        down_payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.DOWN_PAYMENT)
        assert down_payment.met is False
        assert down_payment.required is not None  # 目標總價已設定，缺口金額仍可呈現

    @pytest.mark.scenario("SC-069")
    def test_sc069_both_thresholds_met_down_payment_condition_met(self, service):
        params = _params(
            target_total_price=5_000_000.0, down_payment_ratio=30.0, cash_floor=300_000.0
        )

        checklist = service.assess_triggers(
            params=params,
            bucket_value=1_600_000.0,
            cash_reserve_value=400_000.0,
            forward_result=_forward(None),
            subjective=_subjective(anchor=False, cognition=False),
        )

        down_payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.DOWN_PAYMENT)
        assert down_payment.met is True


class TestAssessTriggersExactBoundaryEquality:
    """客觀觸發條件恰等於門檻時一律視為成立（含等號）（SC-070）。"""

    @pytest.mark.scenario("SC-070")
    def test_sc070_all_three_objective_conditions_exactly_at_threshold_are_met(self, service):
        params = _params(
            target_total_price=5_000_000.0,
            down_payment_ratio=30.0,  # target_amount = 1,500,000
            cash_floor=300_000.0,
            income_threshold=90_000.0,
            monthly_after_tax_income=90_000.0,
            payment_cap_ratio=40.0,
        )

        checklist = service.assess_triggers(
            params=params,
            bucket_value=1_500_000.0,
            cash_reserve_value=300_000.0,
            forward_result=_forward(40.0),
            subjective=_subjective(anchor=False, cognition=False),
        )

        income = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.INCOME)
        down_payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.DOWN_PAYMENT)
        payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.PAYMENT)
        assert income.met is True
        assert down_payment.met is True
        assert payment.met is True

    @pytest.mark.scenario("SC-070")
    def test_sc070_income_one_unit_below_threshold_not_met(self, service):
        params = _params(income_threshold=90_000.0, monthly_after_tax_income=89_999.0)

        checklist = service.assess_triggers(
            params=params,
            bucket_value=0.0,
            cash_reserve_value=0.0,
            forward_result=_forward(None),
            subjective=_subjective(anchor=False, cognition=False),
        )

        income = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.INCOME)
        assert income.met is False

    @pytest.mark.scenario("SC-070")
    def test_sc070_bucket_one_unit_below_target_not_met(self, service):
        params = _params(
            target_total_price=5_000_000.0, down_payment_ratio=30.0, cash_floor=300_000.0
        )

        checklist = service.assess_triggers(
            params=params,
            bucket_value=1_499_999.0,
            cash_reserve_value=300_000.0,
            forward_result=_forward(None),
            subjective=_subjective(anchor=False, cognition=False),
        )

        down_payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.DOWN_PAYMENT)
        assert down_payment.met is False

    @pytest.mark.scenario("SC-070")
    def test_sc070_payment_share_one_tenth_percent_over_cap_not_met(self, service):
        params = _params(payment_cap_ratio=40.0, target_total_price=5_000_000.0)

        checklist = service.assess_triggers(
            params=params,
            bucket_value=0.0,
            cash_reserve_value=0.0,
            forward_result=_forward(40.1),
            subjective=_subjective(anchor=False, cognition=False),
        )

        payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.PAYMENT)
        assert payment.met is False


class TestAssessTriggersPaymentConditionFailClosedOnUnsetIncome:
    """家庭稅後月收未設定、月付占比為 None 時，月付觸發條件視為未達成，fail-closed（SC-072）。"""

    @pytest.mark.scenario("SC-072")
    def test_sc072_payment_condition_not_met_when_income_share_pct_is_none(self, service):
        # 目標總價已設定、月付上限比率正常，但正算月付占比因月收未設定回傳 None：
        # 月付條件不得因「None 恆不大於上限」之類的誤判而視為達成，須明確判為未達成
        params = _params(target_total_price=5_000_000.0, payment_cap_ratio=40.0)

        checklist = service.assess_triggers(
            params=params,
            bucket_value=0.0,
            cash_reserve_value=0.0,
            forward_result=_forward(None),
            subjective=_subjective(anchor=False, cognition=False),
        )

        payment = next(c for c in checklist.conditions if c.key == HOUSE_TRIGGER.PAYMENT)
        assert payment.met is False


# ---------------------------------------------------------------------------
# 買房頁（views/house.py）呈現測試
# ---------------------------------------------------------------------------


class _StubHouseParamRepo:
    """買房參數替身：以 dict（key=HOUSE_PARAM_KEY 值域）注入已存參數。"""

    def __init__(self, params: dict[str, float]):
        self._params = params

    def read_params(self):
        return [
            HouseParamModel(param_key=key, param_value=float(value))
            for key, value in self._params.items()
        ]

    def upsert_param(self, *, param):
        pass


class _StubHoldingRepo:
    """項目主檔替身：固定回傳注入的持有項目清單。"""

    def __init__(self, holdings: list[HoldingModel]):
        self._holdings = holdings

    def list_holdings(self):
        return self._holdings


class _StubRecordRepo:
    """月度紀錄替身：read_all 回傳注入的 DataFrame（比照 Repository.read_all 的形狀）。"""

    def __init__(self, records_df: pd.DataFrame):
        self._records_df = records_df

    def read_all(self):
        return self._records_df


class _StubSubjectiveTriggerRepo:
    """主觀觸發替身：read_triggers 回傳已存勾選狀態；upsert_trigger 呼叫供斷言記錄。

    upsert_error 不為 None 時，upsert_trigger 改為拋出該例外（模擬寫入失敗）。
    """

    def __init__(
        self, triggers: list[SubjectiveTriggerModel], *, upsert_error: Exception | None = None
    ):
        self._triggers = list(triggers)
        self._upsert_error = upsert_error
        self.upserted: list[SubjectiveTriggerModel] = []

    def read_triggers(self):
        return self._triggers

    def upsert_trigger(self, *, trigger):
        if self._upsert_error is not None:
            raise self._upsert_error
        self.upserted.append(trigger)


@pytest.fixture(autouse=True)
def callback_entry_probe():
    """widget callback 入口會驗證連線並讀取快取；替換成回傳測試指定的容器。

    state.calls 記錄探測次數；state.container 不為 None 時回傳它（模擬重連後的新容器），
    否則回傳測試注入 session 的替身容器。
    """
    state = SimpleNamespace(calls=0, container=None)

    def _probe():
        state.calls += 1
        return state.container or st.session_state["container"]

    cache = SimpleNamespace(expire_if_stale=lambda: None)
    with mock.patch("asset_lab.bootstrap.get_resilient_container", side_effect=_probe), \
         mock.patch("asset_lab.bootstrap.get_read_cache", return_value=cache):
        yield state


@pytest.fixture(autouse=True)
def restore_error_details_option():
    """st.set_option 是程序全域設定，測試後還原。"""
    original = st.get_option("client.showErrorDetails")
    yield
    st.set_option("client.showErrorDetails", original)


def _house_page_params(**overrides: float) -> dict[str, float]:
    """五條觸發條件全數可達成的一組虛構買房參數，供 SC-066/067 以 kwargs 覆寫單一欄位。

    自備比率 30% × 目標總價 500 萬＝目標金額 150 萬（與 bucket 現值 160 萬搭配達標）；
    月付上限 40%、驗算利率 2.5%、貸款 30 年（與 AD-7 政策方法論預設同值）。
    """
    base = {
        HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE: 5_000_000.0,
        HOUSE_PARAM_KEY.DOWN_PAYMENT_RATIO: 30.0,
        HOUSE_PARAM_KEY.CASH_FLOOR: 300_000.0,
        HOUSE_PARAM_KEY.INCOME_THRESHOLD: 90_000.0,
        HOUSE_PARAM_KEY.MONTHLY_AFTER_TAX_INCOME: 100_000.0,
        HOUSE_PARAM_KEY.PAYMENT_CAP_RATIO: 40.0,
        HOUSE_PARAM_KEY.TEST_ANNUAL_RATE: 2.5,
        HOUSE_PARAM_KEY.LOAN_YEARS: 30.0,
    }
    base.update(overrides)
    return base


def _house_page_holdings() -> list[HoldingModel]:
    """一個購屋標記定存（bucket）＋一個一般用途活存（現金預備金）。"""
    return [
        HoldingModel(
            holding_id=1,
            name="範例購屋定存",
            kind="asset",
            category=ASSET_CATEGORIES.TIME_DEPOSIT,
            purpose=HOLDING_PURPOSE.HOUSE,
        ),
        HoldingModel(
            holding_id=2,
            name="範例一般活存",
            kind="asset",
            category=ASSET_CATEGORIES.DEMAND_DEPOSIT,
            purpose=HOLDING_PURPOSE.GENERAL,
        ),
    ]


def _house_page_records() -> pd.DataFrame:
    """對應 _house_page_holdings 的最新月市值：bucket 160 萬、現金預備金 40 萬。"""
    return pd.DataFrame(
        [
            {
                "holding_id": 1,
                "year_month": "2026-06",
                "market_value": 1_600_000.0,
                "net_investment": 0.0,
            },
            {
                "holding_id": 2,
                "year_month": "2026-06",
                "market_value": 400_000.0,
                "net_investment": 0.0,
            },
        ]
    )


def _run_house_page(
    *,
    params: dict[str, float],
    holdings: list[HoldingModel],
    records_df: pd.DataFrame,
    triggers: list[SubjectiveTriggerModel],
    trigger_repo: _StubSubjectiveTriggerRepo | None = None,
) -> AppTest:
    """以替身容器跑 views/house.py，回傳已 run() 完成的 AppTest。

    house_service / affordability_service 皆用真正的純運算實作（非替身），使測試走
    完整的頁面編排 → Service 運算鏈路，覆蓋接線正確性；僅 Repository 層以替身脫離
    真實 Turso 依賴。
    """
    container = SimpleNamespace(
        house_param_repo=_StubHouseParamRepo(params),
        holding_repo=_StubHoldingRepo(holdings),
        record_repo=_StubRecordRepo(records_df),
        subjective_trigger_repo=trigger_repo or _StubSubjectiveTriggerRepo(triggers),
        affordability_service=AffordabilityService(),
        house_service=HouseService(),
    )
    at = AppTest.from_file(APP_DIR / "views" / "house.py")
    at.session_state["container"] = container
    at.run()
    return at


class TestHousePageAllTriggersMetShowsCanStart:
    """SC-066：五條觸發條件全部成立時，買房頁顯示 5/5 與「可啟動購屋」。"""

    @pytest.mark.scenario("SC-066")
    def test_sc066_all_five_conditions_met_shows_5_of_5_and_can_start_message(self):
        at = _run_house_page(
            params=_house_page_params(),
            holdings=_house_page_holdings(),
            records_df=_house_page_records(),
            triggers=[
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True),
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=True),
            ],
        )

        assert not at.exception
        met_count_metric = next(m for m in at.metric if m.label == "達成計數")
        assert met_count_metric.value == "5/5"
        assert any(s.value == "可啟動購屋" for s in at.success)

    @pytest.mark.scenario("SC-066")
    def test_sc066_each_condition_individually_shows_achieved(self):
        at = _run_house_page(
            params=_house_page_params(),
            holdings=_house_page_holdings(),
            records_df=_house_page_records(),
            triggers=[
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True),
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=True),
            ],
        )

        status_lines = {m.value for m in at.markdown}
        assert "✅ 收入：達成" in status_lines
        assert "✅ 自備：達成" in status_lines
        assert "✅ 月付：達成" in status_lines
        assert at.checkbox(key="house_trigger_anchor").value is True
        assert at.checkbox(key="house_trigger_cognition").value is True


class TestHousePageNotAllTriggersMetShowsGapList:
    """SC-067：任一觸發條件不成立時，買房頁顯示缺口清單、不顯示「可啟動購屋」。"""

    @pytest.mark.scenario("SC-067")
    def test_sc067_income_and_cognition_unmet_shows_3_of_5_no_can_start_message(self):
        at = _run_house_page(
            params=_house_page_params(monthly_after_tax_income=80_000.0),
            holdings=_house_page_holdings(),
            records_df=_house_page_records(),
            triggers=[
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True),
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=False),
            ],
        )

        assert not at.exception
        met_count_metric = next(m for m in at.metric if m.label == "達成計數")
        assert met_count_metric.value == "3/5"
        assert not any(s.value == "可啟動購屋" for s in at.success)

    @pytest.mark.scenario("SC-067")
    def test_sc067_gap_list_shows_actual_and_required_for_objective_condition(self):
        at = _run_house_page(
            params=_house_page_params(monthly_after_tax_income=80_000.0),
            holdings=_house_page_holdings(),
            records_df=_house_page_records(),
            triggers=[
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True),
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=False),
            ],
        )

        gap_lines = {m.value for m in at.markdown}
        assert "- 收入（實際 80,000 元 vs 門檻 90,000 元）" in gap_lines

    @pytest.mark.scenario("SC-067")
    def test_sc067_gap_list_shows_unchecked_for_subjective_condition(self):
        at = _run_house_page(
            params=_house_page_params(monthly_after_tax_income=80_000.0),
            holdings=_house_page_holdings(),
            records_df=_house_page_records(),
            triggers=[
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True),
                SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=False),
            ],
        )

        gap_lines = {m.value for m in at.markdown}
        assert "- 認知（未勾選）" in gap_lines


class TestHousePageEmptyStateDoesNotCrash:
    """買房頁首次使用（全無參數/主檔/紀錄/勾選）時不得崩潰，且不誤判達標。

    參數完全未設定時應呈現中性姿態（達成計數 0/5、不顯示可啟動購屋），為既有業務語意
    （個人化參數未設定時呈現中性姿態，不誤判達標）在頁面層全空狀態下的延伸。
    """

    @pytest.mark.scenario("SC-056")
    def test_completely_empty_state_renders_without_exception(self):
        empty_columns = ["holding_id", "year_month", "market_value", "net_investment"]
        at = _run_house_page(
            params={},
            holdings=[],
            records_df=pd.DataFrame(columns=empty_columns),
            triggers=[],
        )

        assert not at.exception
        met_count_metric = next(m for m in at.metric if m.label == "達成計數")
        assert met_count_metric.value == "0/5"
        assert not any(s.value == "可啟動購屋" for s in at.success)


class TestHousePageAffordabilityMetricUnsetIncomeDisplay:
    """家庭稅後月收未設定（0）時，買房頁「可負擔總價（反推）」欄位不得顯示為
    「可負擔 0 元」的誤導性結論（SC-056）。
    """

    @pytest.mark.scenario("SC-056")
    def test_sc056_reverse_metric_shows_dash_not_zero_yuan_when_income_unset(self):
        at = _run_house_page(
            params=_house_page_params(monthly_after_tax_income=0.0),
            holdings=_house_page_holdings(),
            records_df=_house_page_records(),
            triggers=[],
        )

        assert not at.exception
        affordability_metric = next(
            m for m in at.metric if m.label == "可負擔總價（反推）"
        )
        assert affordability_metric.value == "—"
        assert affordability_metric.value != "0 元"


class TestHousePageCallbackReconnectAndErrors:
    """SC-111／SC-127：勾選主觀觸發條件的 callback 自行驗證連線，失敗時頁面照常渲染。"""

    @staticmethod
    def _run(*, trigger_repo=None) -> AppTest:
        return _run_house_page(
            params=_house_page_params(),
            holdings=_house_page_holdings(),
            records_df=_house_page_records(),
            triggers=[],
            trigger_repo=trigger_repo,
        )

    @pytest.mark.scenario("SC-111")
    def test_sc111_checkbox_writes_via_verified_container_probed_once(
        self, callback_entry_probe
    ):
        at = self._run()
        assert callback_entry_probe.calls == 0
        # 重連後換了新容器：寫入須走驗證後的新容器，而非上一輪抓住的 repo
        fresh_repo = _StubSubjectiveTriggerRepo([])
        old_container = at.session_state["container"]
        old_repo = old_container.subjective_trigger_repo
        callback_entry_probe.container = SimpleNamespace(
            **{**vars(old_container), "subjective_trigger_repo": fresh_repo}
        )

        at.checkbox(key=f"house_trigger_{HOUSE_TRIGGER.ANCHOR}").check().run()

        assert not at.exception
        assert not at.error
        assert callback_entry_probe.calls == 1
        assert fresh_repo.upserted == [
            SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True)
        ]
        assert old_repo.upserted == []
        assert at.checkbox(key=f"house_trigger_{HOUSE_TRIGGER.ANCHOR}").value is True

    @pytest.mark.scenario("SC-127")
    def test_sc127_unexpected_write_failure_shows_message_and_page_still_renders(
        self, caplog
    ):
        st.set_option("client.showErrorDetails", ERROR_DETAILS.HIDE)
        repo = _StubSubjectiveTriggerRepo(
            [], upsert_error=RuntimeError("libsql native error at /srv/app/secret_path.py")
        )
        at = self._run(trigger_repo=repo)

        with caplog.at_level(logging.ERROR, logger="asset_lab.error_boundary"):
            at.checkbox(key=f"house_trigger_{HOUSE_TRIGGER.ANCHOR}").check().run()

        assert not at.exception
        assert [e.value for e in at.error] == [UNEXPECTED_ERROR_MESSAGE]
        assert [s.value for s in at.subheader if s.value == "觸發條件檢核"] == ["觸發條件檢核"]
        # 訊息在標題下方、其後的頁面內容之前
        order = [el.type for el in at.main]
        assert order.index("title") < order.index("error") < order.index("subheader")
        details = [str(r.exc_info[1]) for r in caplog.records if r.exc_info]
        assert any("libsql native error" in text for text in details)

        # 訊息顯示一次後清除
        at.run()
        assert not at.error

    @pytest.mark.scenario("SC-127")
    def test_sc127_domain_write_failure_shows_original_message(self):
        st.set_option("client.showErrorDetails", ERROR_DETAILS.HIDE)
        repo = _StubSubjectiveTriggerRepo(
            [], upsert_error=PersistenceError("存檔失敗，資料未變更，請重試")
        )
        at = self._run(trigger_repo=repo)

        at.checkbox(key=f"house_trigger_{HOUSE_TRIGGER.COGNITION}").check().run()

        assert not at.exception
        assert [e.value for e in at.error] == ["存檔失敗，資料未變更，請重試"]
