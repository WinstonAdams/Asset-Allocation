"""報酬率區間解析服務。

把使用者選的區間模式換算為 (起月, 訖月) 的純運算層，不碰 I/O、不依賴 Streamlit。
「今天」一律以 Asia/Taipei 判定，使「今年以來」的年初判定在跨年夜不受伺服器時區
（常為 UTC）影響——台北已跨年時，今年即以台北的年份為準。
"""

# ==== 原生（標準庫） ====
from datetime import date, datetime
from zoneinfo import ZoneInfo

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import PERIOD_MODE, TIMEZONE
from asset_lab.core.exceptions import DataValidationError
from asset_lab.core.utils import year_month_add

# 「近一年」涵蓋當月在內共 12 個月，故起點為最新資料月往回 11 個月。
_LAST_12M_BACK = 11


def today_in_timezone(timezone_name: str) -> date:
    """取得指定時區的今天日期。

    Args:
        timezone_name: IANA 時區名稱（如 'Asia/Taipei'）。

    Returns:
        該時區當前的當地日期。
    """
    return datetime.now(ZoneInfo(timezone_name)).date()


class PeriodService:
    """報酬率區間解析。純運算，建構子無依賴。"""

    def __init__(self) -> None:
        """初始化區間服務。本服務無外部依賴，僅做時區換算與月份算術。"""

    def resolve_period(
        self,
        *,
        mode: str,
        latest_ym: str,
        earliest_ym: str,
        custom_start: str | None,
        custom_end: str | None,
    ) -> tuple[str, str]:
        """將區間模式換算為 (起月, 訖月)。

        - inception（自開始記錄以來）：最早有資料月至最新有資料月。
        - ytd（今年以來）：今年 1 月（依 Asia/Taipei 的今天判定）至最新有資料月。
        - last_12m（近一年）：最新有資料月往回 12 個月（含當月）至最新有資料月。
        - custom（自訂）：直接採用指定的起訖月。

        Args:
            mode: 區間模式，須為 'inception' / 'ytd' / 'last_12m' / 'custom' 之一。
            latest_ym: 最新有資料月，'YYYY-MM' 格式，作為非自訂模式的訖點。
            earliest_ym: 最早有資料月，'YYYY-MM' 格式，作為 inception 的起點。
            custom_start: 自訂起月，僅 custom 模式使用，否則可為 None。
            custom_end: 自訂訖月，僅 custom 模式使用，否則可為 None。

        Returns:
            (起月, 訖月) 二元組，皆為 'YYYY-MM' 格式。

        Raises:
            DataValidationError: 模式未知，或自訂模式未提供完整起訖月。
        """
        if mode == PERIOD_MODE.INCEPTION:
            return earliest_ym, latest_ym
        if mode == PERIOD_MODE.YTD:
            current_year = today_in_timezone(TIMEZONE).year
            return f"{current_year:04d}-01", latest_ym
        if mode == PERIOD_MODE.LAST_12M:
            return year_month_add(latest_ym, -_LAST_12M_BACK), latest_ym
        if mode == PERIOD_MODE.CUSTOM:
            if custom_start is None or custom_end is None:
                raise DataValidationError("自訂區間須同時提供起月與訖月")
            return custom_start, custom_end
        raise DataValidationError(f"未知的區間模式：{mode!r}")
