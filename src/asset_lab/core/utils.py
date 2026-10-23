"""專案內部跨層共用的純函式。

僅含無 I/O、無業務流程判斷的年月轉換與序列前處理；
Service 與 Repository 皆可呼叫（見架構合約 §8）。
"""

# ==== 原生（標準庫） ====
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import HOLDING_KIND, MONTHLY_RECORDS_TABLE, YEAR_MONTH_FORMAT
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel

# 'YYYY-MM'：四位數年、兩位數補零的月（01–12）；用於從介面攔下格式不合的年月。
_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# 金額文字：可選負號 + (標準三位一組千分位 或 純數字) + 可選小數部分；
# 千分位分組要求嚴格（如 "1,00,000" 不合），避免使用者誤打多餘或缺漏的 0。
_AMOUNT_PATTERN = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")

# 整數量化目標：配合 ROUND_HALF_UP 做「四捨五入、遠離零」取整。
_INTEGER_QUANTUM = Decimal("1")


def current_year_month(today: date) -> str:
    """將指定日期格式化為所屬的 'YYYY-MM' 年月字串。

    時區判定（「今天」是哪一天）由呼叫端提供的 today 決定（如
    period_service.today_in_timezone 依 Asia/Taipei 換算）；本函式僅做日期到年月字串
    的純轉換，脫離時鐘與時區依賴，使月度錄入頁「預設帶入當月」的推導可注入固定日期做
    單元測試（含跨年邊界）。

    Args:
        today: 用於推導所屬年月的基準日期。

    Returns:
        'YYYY-MM' 格式字串。
    """
    return today.strftime(YEAR_MONTH_FORMAT)


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


def format_amount(value: float | None) -> str:
    """將金額格式化為整數千分位字串。

    金額欄位一律以整數千分位顯示，所見即所存；帶小數的儲存值先四捨五入
    （遠離零）成整數再加千分位逗號，讓顯示格式與輸入格式一致。

    Args:
        value: 金額數值；None 代表尚無資料。

    Returns:
        千分位字串（如 "1,234,567"、"-50,000"）；value 為 None 時回傳空字串。
    """
    if value is None:
        return ""
    rounded = int(Decimal(str(value)).quantize(_INTEGER_QUANTUM, rounding=ROUND_HALF_UP))
    sign = "-" if rounded < 0 else ""
    return f"{sign}{abs(rounded):,}"


def parse_amount(text: str | None, *, field_label: str) -> float:
    """將使用者輸入的金額文字解析為數值。

    先做 NFKC 正規化，讓全形數字／全形逗號（中文輸入法常見）等價於半形
    輸入；千分位分組比對從嚴，攔下「1,00,000」這類多打或少打 0 的輸入。
    通過格式檢查後四捨五入（遠離零）成整數，對齊金額欄「整數千分位」的
    顯示規格。

    Args:
        text: 使用者輸入的原始文字；None 或空字串視為未填。
        field_label: 欄位名稱，用於解析失敗時的錯誤訊息。

    Returns:
        解析後的金額數值（整數值，以 float 回傳）。

    Raises:
        DataValidationError: 輸入為 None、空字串，或格式不符千分位規則。訊息只帶欄位
            名稱、不帶輸入原文：例外會被頁面寫進 log，原文可能就是金額；使用者在輸入框
            仍看得到自己打的內容。
    """
    normalized = unicodedata.normalize("NFKC", text).strip() if text is not None else ""
    if not normalized or _AMOUNT_PATTERN.match(normalized) is None:
        raise DataValidationError(f"{field_label}輸入無效，請輸入正確的金額格式")
    rounded = int(
        Decimal(normalized.replace(",", "")).quantize(_INTEGER_QUANTUM, rounding=ROUND_HALF_UP)
    )
    return float(rounded)
