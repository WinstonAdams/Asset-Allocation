"""專案內部跨層共用的純函式。

僅含無 I/O、無業務流程判斷的年月轉換與序列前處理；
Service 與 Repository 皆可呼叫（見架構合約 §8）。
"""

# ==== 原生（標準庫） ====
import re

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import HOLDING_KIND, MONTHLY_RECORDS_TABLE
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel

# 'YYYY-MM'：四位數年、兩位數補零的月（01–12）；用於從介面攔下格式不合的年月。
_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def parse_year_month(year_month: str) -> tuple[int, int]:
    """將 'YYYY-MM' 字串解析為 (年, 月)。

    Args:
        year_month: 'YYYY-MM' 格式的月份字串，月份須補零至兩位（01–12）。

    Returns:
        (year, month) 整數元組。

    Raises:
        DataValidationError: 字串不符 'YYYY-MM' 格式（含月份越界）。
    """
    match = _YEAR_MONTH_PATTERN.match(year_month) if isinstance(year_month, str) else None
    if match is None:
        raise DataValidationError(f"年月格式須為 'YYYY-MM'，收到：{year_month!r}")
    return int(match.group(1)), int(match.group(2))


def year_month_add(year_month: str, months: int) -> str:
    """對 'YYYY-MM' 做月份加減並回傳 'YYYY-MM'，正確處理跨年進退位。

    Args:
        year_month: 起始月份，'YYYY-MM' 格式。
        months: 位移月數，正為向後、負為向前、0 為原月份。

    Returns:
        位移後的 'YYYY-MM' 字串。

    Raises:
        DataValidationError: year_month 不符 'YYYY-MM' 格式。
    """
    year, month = parse_year_month(year_month)
    # 以 0-based 月索引運算，避免 1-based 取餘的邊界錯誤
    total = year * 12 + (month - 1) + months
    new_year, new_month_index = divmod(total, 12)
    return f"{new_year:04d}-{new_month_index + 1:02d}"


def months_between(start_ym: str, end_ym: str) -> int:
    """計算兩個 'YYYY-MM' 相差的月數（end 減 start），同月為 0。

    用於由區間起訖月推算涵蓋的月跨度（涵蓋月數 = 相差月數 + 1）。

    Args:
        start_ym: 起始月份，'YYYY-MM' 格式。
        end_ym: 結束月份，'YYYY-MM' 格式。

    Returns:
        end_ym 減 start_ym 的月數差；end 早於 start 時為負值。

    Raises:
        DataValidationError: 任一參數不符 'YYYY-MM' 格式。
    """
    start_year, start_month = parse_year_month(start_ym)
    end_year, end_month = parse_year_month(end_ym)
    return (end_year - start_year) * 12 + (end_month - start_month)


def filter_asset_records(range_df: pd.DataFrame, holdings: list[HoldingModel]) -> pd.DataFrame:
    """從月度紀錄篩出資產項目的列；負債一律排除。

    配置與報酬率口徑皆「僅計資產」，故 ReturnService 與 AllocationService 都需先以此
    過濾掉負債列。抽為共用純函式，使「負債排除」口徑單一定義、兩個 Service 不各自重複。

    Args:
        range_df: 月度紀錄 DataFrame，含 holding_id 欄。
        holdings: 項目主檔清單，用於辨識哪些 holding_id 為資產。

    Returns:
        僅含資產項目列的 DataFrame；輸入為空時原樣回傳。
    """
    if range_df.empty:
        return range_df
    asset_ids = {h.holding_id for h in holdings if h.kind == HOLDING_KIND.ASSET}
    return range_df[range_df[MONTHLY_RECORDS_TABLE.HOLDING_ID].isin(asset_ids)]
