# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.core.access import AccessReason, evaluate_access

# 測試用虛構 email（非真實個資，遵守敏感資料護欄）。
OWNER_EMAIL = "owner@example.test"
OTHER_EMAIL = "stranger@example.test"
ALLOWED = frozenset({OWNER_EMAIL})


class TestSc033OwnerGranted:
    """SC-033：本人 email 登入後可進入並看到財務資料。"""

    @pytest.mark.scenario("SC-033")
    def test_sc033_logged_in_owner_is_granted(self):
        # 已登入且 email 在受控允許清單 → 放行
        decision = evaluate_access(
            is_logged_in=True, email=OWNER_EMAIL, allowed_emails=ALLOWED
        )
        assert decision.granted is True
        assert decision.reason is AccessReason.GRANTED

    @pytest.mark.scenario("SC-033")
    def test_sc033_owner_granted_when_multiple_emails_allowed(self):
        # 清單可擴充多人；本人在其中一員即放行
        decision = evaluate_access(
            is_logged_in=True,
            email=OWNER_EMAIL,
            allowed_emails=frozenset({OTHER_EMAIL, OWNER_EMAIL}),
        )
        assert decision.granted is True
        assert decision.reason is AccessReason.GRANTED


class TestSc033NotLoggedIn:
    """SC-033：未登入前須顯示登入入口，不渲染任何頁面、不載入財務資料。"""

    @pytest.mark.scenario("SC-033")
    def test_sc033_not_logged_in_is_denied_with_login_required(self):
        # 未登入 → 擋下，理由為「需登入」（供守門顯示登入入口）
        decision = evaluate_access(
            is_logged_in=False, email=None, allowed_emails=ALLOWED
        )
        assert decision.granted is False
        assert decision.reason is AccessReason.NOT_LOGGED_IN

    @pytest.mark.scenario("SC-033")
    def test_sc033_not_logged_in_takes_priority_over_email_value(self):
        # 即使帶有看似合法的 email，只要尚未登入仍視為未登入而擋下
        decision = evaluate_access(
            is_logged_in=False, email=OWNER_EMAIL, allowed_emails=ALLOWED
        )
        assert decision.granted is False
        assert decision.reason is AccessReason.NOT_LOGGED_IN


class TestSc034StrangerDenied:
    """SC-034：非本人 email 登入後被擋下，看不到任何財務資料。"""

    @pytest.mark.scenario("SC-034")
    def test_sc034_logged_in_stranger_is_denied(self):
        # 已登入但 email 不在允許清單 → 擋下，理由為「非本人」
        decision = evaluate_access(
            is_logged_in=True, email=OTHER_EMAIL, allowed_emails=ALLOWED
        )
        assert decision.granted is False
        assert decision.reason is AccessReason.EMAIL_NOT_ALLOWED

    @pytest.mark.scenario("SC-034")
    def test_sc034_logged_in_with_empty_allowlist_denies_everyone(self):
        # 允許清單為空時，任何登入者皆非本人 → 一律擋下（不會誤放行）
        decision = evaluate_access(
            is_logged_in=True, email=OWNER_EMAIL, allowed_emails=frozenset()
        )
        assert decision.granted is False
        assert decision.reason is AccessReason.EMAIL_NOT_ALLOWED

    @pytest.mark.scenario("SC-034")
    def test_sc034_logged_in_without_email_is_denied(self):
        # 已登入但取不到 email（None）→ 無法證明為本人 → 擋下
        decision = evaluate_access(
            is_logged_in=True, email=None, allowed_emails=ALLOWED
        )
        assert decision.granted is False
        assert decision.reason is AccessReason.EMAIL_NOT_ALLOWED

    @pytest.mark.scenario("SC-034")
    def test_sc034_logged_in_with_empty_email_is_denied(self):
        # 已登入但 email 為空字串 → 不在清單 → 擋下
        decision = evaluate_access(
            is_logged_in=True, email="", allowed_emails=ALLOWED
        )
        assert decision.granted is False
        assert decision.reason is AccessReason.EMAIL_NOT_ALLOWED


class TestAccessGuardrail:
    """守門通則：拒絕決策一律不放行（看不到任何財務資料）。"""

    @pytest.mark.scenario("SC-034")
    def test_any_denied_decision_never_grants(self):
        # 任一非放行決策的 granted 皆為 False，杜絕「擋下卻仍看得到資料」
        denied = [
            evaluate_access(is_logged_in=False, email=None, allowed_emails=ALLOWED),
            evaluate_access(is_logged_in=True, email=OTHER_EMAIL, allowed_emails=ALLOWED),
            evaluate_access(is_logged_in=True, email=None, allowed_emails=ALLOWED),
        ]
        assert all(d.granted is False for d in denied)


class TestEmailNormalization:
    """SC-039：本人 email 大小寫 / 前後空白差異時，正規化後仍視為本人。

    SC-039 邊界區分兩種獨立觸發（「僅大小寫不同」「僅前後空白不同」），故分離驗證。
    """

    @pytest.mark.scenario("SC-039")
    def test_case_only_difference_email_matches_lowercase_allowlist(self):
        # 僅大小寫不同（無多餘空白）：整個 email 轉小寫後比對，仍視為本人
        decision = evaluate_access(
            is_logged_in=True,
            email="OWNER@Example.TEST",
            allowed_emails=ALLOWED,
        )
        assert decision.granted is True
        assert decision.reason is AccessReason.GRANTED

    @pytest.mark.scenario("SC-039")
    def test_whitespace_only_difference_email_matches_allowlist(self):
        # 僅前後空白不同（大小寫一致）：去前後空白後比對，仍視為本人
        decision = evaluate_access(
            is_logged_in=True,
            email="  owner@example.test  ",
            allowed_emails=ALLOWED,
        )
        assert decision.granted is True
        assert decision.reason is AccessReason.GRANTED

    @pytest.mark.scenario("SC-039")
    def test_uppercase_and_whitespace_email_matches_lowercase_allowlist(self):
        # 大小寫 + 前後空白同時不同：正規化（去空白 + 轉小寫）後比對，仍視為本人
        decision = evaluate_access(
            is_logged_in=True,
            email="  OWNER@Example.TEST  ",
            allowed_emails=ALLOWED,
        )
        assert decision.granted is True
        assert decision.reason is AccessReason.GRANTED
