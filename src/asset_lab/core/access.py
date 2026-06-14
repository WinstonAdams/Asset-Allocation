"""登入守門的純判定邏輯。

把「已登入的使用者是否為允許的本人」抽成不依賴 Streamlit 的純函式，
讓守門決策可獨立以單元測試驗證三種結果（未登入擋下、本人放行、非本人擋下）。
st.login() 按鈕渲染、st.stop()、st.user.email 取值等 Streamlit 副作用屬入口
串接層的職責，本模組只回傳結構化決策，不觸碰 runtime，也不讀取任何機密。

允許登入的 email 屬個資且依部署環境而異，一律由呼叫端從設定（st.secrets）注入，
本模組不持有也不寫死任何 email。
"""

# ==== 原生（標準庫） ====
from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
# 無


class AccessReason(Enum):
    """守門決策的判定理由，供串接層決定要顯示登入入口或拒絕訊息。"""

    GRANTED = "granted"
    NOT_LOGGED_IN = "not_logged_in"
    EMAIL_NOT_ALLOWED = "email_not_allowed"


@dataclass(frozen=True)
class AccessDecision:
    """單次守門判定結果。

    Attributes:
        granted: 是否放行進入；為 False 時表示應停止渲染、不載入任何財務資料。
        reason: 判定理由，granted 為 True 時恆為 GRANTED。
    """

    granted: bool
    reason: AccessReason


def _normalize_email(email: str) -> str:
    """將 email 正規化為比對用字面。

    身分供應商回傳的 email 可能夾帶前後空白或大小寫差異，去空白並轉小寫後比對，
    避免本人因字面細節被誤擋在外。

    Args:
        email: 原始 email 字串。

    Returns:
        去除前後空白並轉為小寫的 email。
    """
    return email.strip().lower()


def evaluate_access(
    *,
    is_logged_in: bool,
    email: str | None,
    allowed_emails: Collection[str],
) -> AccessDecision:
    """判定一名使用者是否獲准進入。

    守門以三段優先序判定：尚未登入一律先擋（顯示登入入口）；已登入但無法證明為
    清單內本人（無 email 或不在允許清單）則擋下拒絕；唯有已登入且 email 命中允許
    清單才放行。任一擋下決策的 granted 皆為 False，確保非本人看不到任何財務資料。

    Args:
        is_logged_in: 使用者是否已完成登入。
        email: 已登入使用者的 email；尚未取得時為 None。
        allowed_emails: 受控允許清單，由呼叫端從設定注入；空清單代表不放行任何人。

    Returns:
        AccessDecision，含是否放行與判定理由。
    """
    if not is_logged_in:
        return AccessDecision(granted=False, reason=AccessReason.NOT_LOGGED_IN)

    if not email:
        return AccessDecision(granted=False, reason=AccessReason.EMAIL_NOT_ALLOWED)

    normalized_allowed = {_normalize_email(allowed) for allowed in allowed_emails}
    if _normalize_email(email) not in normalized_allowed:
        return AccessDecision(granted=False, reason=AccessReason.EMAIL_NOT_ALLOWED)

    return AccessDecision(granted=True, reason=AccessReason.GRANTED)
