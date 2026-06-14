# ==== 原生（標準庫） ====
from datetime import UTC
from unittest import mock

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.services.period_service import PeriodService


class TestResolvePeriod:
    """resolve_period：把區間模式換算為 (起月, 訖月)，今天一律以 Asia/Taipei 判定。"""

    @pytest.mark.scenario("SC-021")
    def test_sc021_inception_spans_full_range(self):
        # 自開始記錄以來：起點為最早有資料月、訖點為最新資料月
        start, end = PeriodService().resolve_period(
            mode="inception",
            latest_ym="2026-05",
            earliest_ym="2024-01",
            custom_start=None,
            custom_end=None,
        )
        assert (start, end) == ("2024-01", "2026-05")

    @pytest.mark.scenario("SC-021")
    def test_sc021_ytd_starts_at_january_of_current_year(self):
        # 今年以來：當年 1 月至最新資料月；當年由 Asia/Taipei 的今天決定
        with _today("2026-07-09"):
            start, end = PeriodService().resolve_period(
                mode="ytd",
                latest_ym="2026-05",
                earliest_ym="2024-01",
                custom_start=None,
                custom_end=None,
            )
        assert (start, end) == ("2026-01", "2026-05")

    @pytest.mark.scenario("SC-021")
    def test_sc021_last_12m_counts_back_twelve_months_inclusive(self):
        # 近一年：最新資料月往回 12 個月（含當月，故 2026-05 起點為 2025-06）
        start, end = PeriodService().resolve_period(
            mode="last_12m",
            latest_ym="2026-05",
            earliest_ym="2024-01",
            custom_start=None,
            custom_end=None,
        )
        assert (start, end) == ("2025-06", "2026-05")

    @pytest.mark.scenario("SC-021")
    def test_sc021_custom_uses_specified_start_and_end(self):
        # 自訂起訖月：直接採用指定區間
        start, end = PeriodService().resolve_period(
            mode="custom",
            latest_ym="2026-05",
            earliest_ym="2024-01",
            custom_start="2025-01",
            custom_end="2025-12",
        )
        assert (start, end) == ("2025-01", "2025-12")

    @pytest.mark.scenario("SC-021")
    def test_sc021_ytd_uses_taipei_timezone_for_year_boundary(self):
        # 「今天」一律以 Asia/Taipei 判定：跨年夜 UTC 仍是去年、台北已是今年
        # 2025-12-31 23:30 UTC ＝ 台北 2026-01-01 07:30，YTD 當年應為 2026
        with _today_utc("2025-12-31T23:30:00"):
            start, _ = PeriodService().resolve_period(
                mode="ytd",
                latest_ym="2026-01",
                earliest_ym="2024-01",
                custom_start=None,
                custom_end=None,
            )
        assert start == "2026-01"

    @pytest.mark.scenario("SC-021")
    def test_sc021_unknown_mode_rejected(self):
        # 未知模式不靜默放行，攔下避免回傳無意義區間
        with pytest.raises(DataValidationError):
            PeriodService().resolve_period(
                mode="weekly",
                latest_ym="2026-05",
                earliest_ym="2024-01",
                custom_start=None,
                custom_end=None,
            )

    @pytest.mark.scenario("SC-021")
    def test_sc021_custom_without_dates_rejected(self):
        # 自訂模式未提供起訖月：無從決定區間，攔下
        with pytest.raises(DataValidationError):
            PeriodService().resolve_period(
                mode="custom",
                latest_ym="2026-05",
                earliest_ym="2024-01",
                custom_start=None,
                custom_end=None,
            )


def _today(taipei_date: str):
    """以固定的 Asia/Taipei 當地日期取代 PeriodService 內部的今天判定。"""
    from datetime import date

    year, month, day = (int(part) for part in taipei_date.split("-"))
    return mock.patch(
        "asset_lab.services.period_service.today_in_timezone",
        return_value=date(year, month, day),
    )


def _today_utc(utc_iso: str):
    """以固定的 UTC 時刻凍結系統時鐘，驗證內部時區換算落在 Asia/Taipei。"""
    from datetime import datetime

    fixed = datetime.fromisoformat(utc_iso).replace(tzinfo=UTC)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)

    return mock.patch("asset_lab.services.period_service.datetime", _FrozenDateTime)
