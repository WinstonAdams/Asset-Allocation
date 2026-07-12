"""總覽頁（views/overview.py）的呈現資料組裝層——純函式，定位比照 charts.py。

把 `ProtocolService.assess()` 的判定結果（`ProtocolStatus`）轉成總覽頁可直接渲染的
資料：依 level_code 查 `constants.PROTOCOL_LEVELS` 取得該級必做/禁止摘要，並依資料
充足度旗標決定是否顯示警示與回撤數值、切換對應的中性文案。不碰 `st.*`、不做任何
等級判定的業務運算（判定歸 `ProtocolService`），只負責「判定結果 → 呈現資料」的轉換
契約，供 Page 層委派使用，且可獨立單元測試而不需驅動 Streamlit runtime——views/*.py
頁面檔尾端皆無條件呼叫 `render()`（觸發 `st.session_state` 存取），不適合被一般
`import` 直接載入，故可測邏輯抽離至本模組。

資料不足（`no_data` / `insufficient_data`）時，`ProtocolStatus.level_code` 已由
`ProtocolService.assess()` 退回 L0；本模組據此關閉警示、隱藏回撤數值，僅切換「完全
無紀錄」與「有資料但不足」兩種中性文案。
"""

# ==== 原生（標準庫） ====
from dataclasses import dataclass

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import PROTOCOL_LEVEL_CODE, PROTOCOL_LEVELS, ProtocolLevelSpec
from asset_lab.models.results import ProtocolStatus

_LEVEL_SPEC_BY_CODE = {spec.code: spec for spec in PROTOCOL_LEVELS}

# ProtocolService.assess() 定義的資料充足度旗標。
_STATUS_NO_DATA = "no_data"
_STATUS_INSUFFICIENT_DATA = "insufficient_data"
_INSUFFICIENT_STATUSES = frozenset({_STATUS_NO_DATA, _STATUS_INSUFFICIENT_DATA})

# 資料不足兩種情境的中性文案：完全無紀錄 vs 有資料但不足，避免使用者混淆兩種狀態。
NO_DATA_MESSAGE = "尚無資料，請先至月度錄入輸入"
INSUFFICIENT_DATA_MESSAGE = "資料尚不足，暫不評估大跌等級"

# 資料充足且判定進入該等級時才顯示警示；L0（平時）不警示。
_ALERT_LEVELS = frozenset({PROTOCOL_LEVEL_CODE.L1, PROTOCOL_LEVEL_CODE.L2, PROTOCOL_LEVEL_CODE.L3})

# 回撤（≤0 小數）換算百分比顯示的乘數。
_PERCENT_MULTIPLIER = 100


@dataclass(frozen=True)
class OverviewPresentation:
    """總覽頁單一畫面所需的呈現資料（狀態 → 呈現，純資料、無 Streamlit 依賴）。"""

    level_spec: ProtocolLevelSpec
    show_alert: bool
    neutral_message: str | None
    drawdown_percent: float | None


def level_spec_for(level_code: str) -> ProtocolLevelSpec:
    """依等級代碼查表取得對應的展示規格（必做/禁止/回撤帶/標籤）。

    Args:
        level_code: 'L0'~'L3'。

    Returns:
        對應等級的 ProtocolLevelSpec。

    Raises:
        KeyError: level_code 不在 PROTOCOL_LEVELS 涵蓋範圍（不應發生於正常呼叫路徑，
            ProtocolService.assess 只會回傳 'L0'~'L3'）。
    """
    return _LEVEL_SPEC_BY_CODE[level_code]


def resolve_presentation(status: ProtocolStatus) -> OverviewPresentation:
    """把 ProtocolStatus 轉換為總覽頁呈現資料。

    資料充足（status='ok'）時依實際等級查表呈現，L1–L3 顯示警示、回撤數值以百分比
    呈現；資料不足（'no_data'/'insufficient_data'）時一律關閉警示、隱藏回撤數值，
    並依情況切換「完全無紀錄」或「有資料但不足」的中性文案——不誤導使用者以為系統
    已判定大跌等級。

    Args:
        status: ProtocolService.assess() 的判定結果。

    Returns:
        OverviewPresentation，供 Page 層直接渲染。
    """
    is_sufficient = status.status not in _INSUFFICIENT_STATUSES
    return OverviewPresentation(
        level_spec=level_spec_for(status.level_code),
        show_alert=is_sufficient and status.level_code in _ALERT_LEVELS,
        neutral_message=None if is_sufficient else _neutral_message_for(status.status),
        drawdown_percent=(
            status.drawdown * _PERCENT_MULTIPLIER
            if is_sufficient and status.drawdown is not None
            else None
        ),
    )


def _neutral_message_for(status_flag: str) -> str:
    """依資料充足度旗標決定中性文案（完全無紀錄 vs 有資料但不足）。"""
    if status_flag == _STATUS_NO_DATA:
        return NO_DATA_MESSAGE
    return INSUFFICIENT_DATA_MESSAGE
