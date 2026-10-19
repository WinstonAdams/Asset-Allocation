"""股票/ETF（總成本）與保險（累計保費）推算月淨投入的核心運算（純運算，無 I/O、無 Streamlit）。"""

# ==== 原生（標準庫） ====
import math

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import (
    CostBasisEditorPrefill,
    NetInvestmentDerivation,
    PremiumEditorPrefill,
)


class CostBasisService:
    """股票/ETF 總成本與保險累計保費推算淨投入（純運算：無 I/O、無 Streamlit）。"""

    def __init__(
        self, *, cost_basis_categories: frozenset[str], premium_categories: frozenset[str]
    ) -> None:
        """初始化總成本推算服務。

        Args:
            cost_basis_categories: 走總成本推算的資產分類集合（由 bootstrap 注入）。
            premium_categories: 走累計保費推算的資產分類集合（由 bootstrap 注入）。
        """
        self.cost_basis_categories = cost_basis_categories
        self.premium_categories = premium_categories

    def uses_cost_basis(self, *, holding: HoldingModel) -> bool:
        """判斷項目是否以總成本＋已實現收益推算月淨投入。

        負債沒有分類（category 為 None），一律不適用；其餘分類仍手填市值/餘額與
        淨投入。

        Args:
            holding: 項目主檔。

        Returns:
            項目目前分類屬於總成本推算範圍時為 True。
        """
        return holding.category in self.cost_basis_categories

    def derive(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
        total_cost: float,
        realized_pnl: float,
        cash_dividend: float,
    ) -> NetInvestmentDerivation:
        """推算股票/ETF 項目當月淨投入。

        前期總成本只看該項目年月早於 year_month 的紀錄：沒有任何前期紀錄時取項目
        初始成本；前一筆（年月最接近 year_month 的一筆）已填總成本時直接沿用；
        前一筆是本功能上線前建立的舊制列（未填總成本）時，改以「初始成本＋該月
        以前所有紀錄的淨投入加總」估算，並標示為過渡期估算值，讓呼叫端提醒使用者
        這個估算可能與券商實際總成本有落差。

        Args:
            holding: 項目主檔，須為走總成本推算的分類。
            records: 該項目的全部月度紀錄（呼叫端保證只含該項目、任意順序）。
            year_month: 本次要推算的年月（'YYYY-MM'）。
            total_cost: 本月使用者輸入的目前總成本。
            realized_pnl: 本月已實現損益（可為負，認列虧損）。
            cash_dividend: 本月現金股利（不可為負）。

        Returns:
            前期總成本、是否為過渡期估算、推算出的本月淨投入。

        Raises:
            DataValidationError: 項目分類不適用總成本推算，或現金股利為負時拋出。
        """
        self._ensure_uses_cost_basis(holding=holding)
        self._ensure_cash_dividend_non_negative(cash_dividend=cash_dividend)

        return self._derive_from_realized_income(
            holding=holding,
            records=records,
            year_month=year_month,
            total_cost=total_cost,
            realized_income=realized_pnl + cash_dividend,
        )

    def _derive_from_realized_income(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
        total_cost: float,
        realized_income: float,
    ) -> NetInvestmentDerivation:
        """以已實現收益合計推算淨投入（derive 與連動重算共用，不做輸入驗證）。

        Args:
            holding: 項目主檔。
            records: 該項目的全部月度紀錄。
            year_month: 推算的年月（'YYYY-MM'）。
            total_cost: 該月總成本。
            realized_income: 該月已實現收益合計（已實現損益＋現金股利）。

        Returns:
            前期總成本、是否為過渡期估算、推算出的淨投入。
        """
        prior_records = sorted(
            (record for record in records if record.year_month < year_month),
            key=lambda record: record.year_month,
        )

        if not prior_records:
            previous_total_cost = holding.initial_cost or 0.0
            is_transition_estimate = False
        else:
            latest_prior = prior_records[-1]
            if latest_prior.total_cost is not None:
                previous_total_cost = latest_prior.total_cost
                is_transition_estimate = False
            else:
                previous_total_cost = (holding.initial_cost or 0.0) + sum(
                    record.net_investment for record in prior_records
                )
                is_transition_estimate = True

        net_investment = (total_cost - previous_total_cost) - realized_income

        return NetInvestmentDerivation(
            previous_total_cost=previous_total_cost,
            is_transition_estimate=is_transition_estimate,
            net_investment=net_investment,
        )

    def plan_save(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
        market_value: float,
        total_cost: float,
        realized_pnl: float,
        cash_dividend: float,
    ) -> list[MonthlyRecordModel]:
        """規劃股票/ETF 存檔需要寫入的所有列，含連動重算受影響的後續新制列。

        存檔列本身的淨投入照 `derive` 推算；異動月份之後、依時間順序排列的每一筆
        新制列（`total_cost` 不為 None）都用最新狀態重新推算一次，因為過渡規則
        下前期總成本可能取自跨越多筆的淨投入加總。只回傳推算值和既存值不同
        （容許浮點誤差）的列，冪等的重算不會被回傳，也就不會被多寫入。

        Args:
            holding: 項目主檔，須為走總成本推算的分類。
            records: 該項目異動前的全部月度紀錄（呼叫端保證只含該項目、任意順序）。
            year_month: 本次存檔的年月（'YYYY-MM'）。
            market_value: 本月現值。
            total_cost: 本月使用者輸入的目前總成本。
            realized_pnl: 本月已實現損益（可為負，認列虧損）。
            cash_dividend: 本月現金股利（不可為負）。

        Returns:
            [存檔列, *異動月份之後推算值有變的新制列]，依年月排序。

        Raises:
            DataValidationError: 項目分類不適用總成本推算，或現金股利為負時拋出。
        """
        derivation = self.derive(
            holding=holding,
            records=records,
            year_month=year_month,
            total_cost=total_cost,
            realized_pnl=realized_pnl,
            cash_dividend=cash_dividend,
        )
        saved_record = MonthlyRecordModel(
            holding_id=holding.holding_id,
            year_month=year_month,
            market_value=market_value,
            net_investment=derivation.net_investment,
            total_cost=total_cost,
            realized_income=realized_pnl + cash_dividend,
            cash_dividend=cash_dividend,
        )

        working_records = [record for record in records if record.year_month != year_month]
        working_records.append(saved_record)

        changed_following = self._recalculate_following(
            holding=holding, working_records=working_records, cutoff_year_month=year_month
        )

        return [saved_record, *changed_following]

    def plan_delete(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
    ) -> list[MonthlyRecordModel]:
        """規劃股票/ETF 刪除某月紀錄後，連動重算受影響的後續新制列。

        刪除後緊接的下一筆列如果是本功能上線前建立的舊制列，不會被重算；真正
        受影響的是往後第一筆新制列，因為它的前期總成本可能是用過渡規則從初始
        成本加總淨投入估算出來的，刪掉其中一筆會改變加總結果。

        Args:
            holding: 項目主檔，須為走總成本推算的分類。
            records: 該項目刪除前的全部月度紀錄（呼叫端保證只含該項目、任意順序）。
            year_month: 要刪除的年月（'YYYY-MM'）。

        Returns:
            異動月份之後推算值有變的新制列，依年月排序；沒有任何列受影響時為空清單。

        Raises:
            DataValidationError: 項目分類不是股票/ETF 或保險時拋出。
        """
        self._ensure_uses_cost_chain(holding=holding)

        working_records = [record for record in records if record.year_month != year_month]

        return self._recalculate_following(
            holding=holding, working_records=working_records, cutoff_year_month=year_month
        )

    def build_cost_basis_prefill(
        self, *, records: list[MonthlyRecordModel], year_month: str
    ) -> CostBasisEditorPrefill:
        """算出股票/ETF 錄入框的帶入值：該月已有紀錄就照存的值，沒有則為現行預設。

        總成本／現值為空白（None）或該月無紀錄時保持空白，避免把空白存成 0（0 代表清倉）。
        已實現損益由存下來的合計扣除現金股利還原；現金股利為空白的舊紀錄，
        合計全數視為已實現損益。

        Args:
            records: 該項目的月度紀錄（呼叫端保證只含該項目）。
            year_month: 選取的月份，'YYYY-MM' 格式。

        Returns:
            帶入值；無相符紀錄時總成本與現值留空（None），已實現損益與現金股利為 0。
        """
        for record in records:
            if record.year_month == year_month:
                cash_dividend = record.cash_dividend or 0.0
                return CostBasisEditorPrefill(
                    total_cost=record.total_cost,
                    market_value=record.market_value,
                    realized_pnl=(record.realized_income or 0.0) - cash_dividend,
                    cash_dividend=cash_dividend,
                )
        return CostBasisEditorPrefill(
            total_cost=None, market_value=None, realized_pnl=0.0, cash_dividend=0.0
        )

    def uses_premium(self, *, holding: HoldingModel) -> bool:
        """判斷項目是否以累計已繳保費＋本月領回推算月淨投入。

        Args:
            holding: 項目主檔。

        Returns:
            項目目前分類屬於保險推算範圍時為 True。
        """
        return holding.category in self.premium_categories

    def derive_premium(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
        cumulative_premium: float,
        withdrawal: float,
    ) -> NetInvestmentDerivation:
        """推算保險項目當月淨投入：(本月累計保費 − 前期累計保費) − 本月領回。

        前期累計保費的取法（含舊制列的過渡估算）與股票/ETF 的前期總成本相同；
        回傳的 previous_total_cost 即前期累計保費。

        Args:
            holding: 項目主檔，須為保險分類。
            records: 該項目的全部月度紀錄（呼叫端保證只含該項目、任意順序）。
            year_month: 本次要推算的年月（'YYYY-MM'）。
            cumulative_premium: 本月累計已繳保費。
            withdrawal: 本月領回金額（不可為負）。

        Returns:
            前期累計保費、是否為過渡期估算、推算出的本月淨投入。

        Raises:
            DataValidationError: 項目分類不是保險，或領回金額為負時拋出。
        """
        self._ensure_uses_premium(holding=holding)
        self._ensure_withdrawal_non_negative(withdrawal=withdrawal)

        return self._derive_from_realized_income(
            holding=holding,
            records=records,
            year_month=year_month,
            total_cost=cumulative_premium,
            realized_income=withdrawal,
        )

    def plan_save_premium(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
        surrender_value: float,
        cumulative_premium: float,
        withdrawal: float,
    ) -> list[MonthlyRecordModel]:
        """規劃保險存檔需要寫入的所有列，含連動重算受影響的後續新制列。

        存檔列：解約金存為市值、累計保費存為總成本、領回存為已實現收益。連動
        重算規則與股票/ETF 相同（只回傳推算值有變的新制列）。

        Args:
            holding: 項目主檔，須為保險分類。
            records: 該項目異動前的全部月度紀錄（呼叫端保證只含該項目、任意順序）。
            year_month: 本次存檔的年月（'YYYY-MM'）。
            surrender_value: 本月解約金。
            cumulative_premium: 本月累計已繳保費。
            withdrawal: 本月領回金額（不可為負）。

        Returns:
            [存檔列, *異動月份之後推算值有變的新制列]，依年月排序。

        Raises:
            DataValidationError: 項目分類不是保險，或領回金額為負時拋出。
        """
        derivation = self.derive_premium(
            holding=holding,
            records=records,
            year_month=year_month,
            cumulative_premium=cumulative_premium,
            withdrawal=withdrawal,
        )
        saved_record = MonthlyRecordModel(
            holding_id=holding.holding_id,
            year_month=year_month,
            market_value=surrender_value,
            net_investment=derivation.net_investment,
            total_cost=cumulative_premium,
            realized_income=withdrawal,
            cash_dividend=None,
        )

        working_records = [record for record in records if record.year_month != year_month]
        working_records.append(saved_record)

        changed_following = self._recalculate_following(
            holding=holding, working_records=working_records, cutoff_year_month=year_month
        )

        return [saved_record, *changed_following]

    def build_premium_prefill(
        self, *, records: list[MonthlyRecordModel], year_month: str
    ) -> PremiumEditorPrefill:
        """算出保險錄入框的帶入值：該月已有紀錄就照存的值，沒有則累計保費／解約金留空。

        累計保費／解約金為空白（None）或該月無紀錄時保持空白，避免把空白存成 0。

        Args:
            records: 該項目的月度紀錄（呼叫端保證只含該項目）。
            year_month: 選取的月份，'YYYY-MM' 格式。

        Returns:
            帶入值；無相符紀錄時累計保費與解約金留空（None），領回為 0。
        """
        for record in records:
            if record.year_month == year_month:
                return PremiumEditorPrefill(
                    cumulative_premium=record.total_cost,
                    surrender_value=record.market_value,
                    withdrawal=record.realized_income or 0.0,
                )
        return PremiumEditorPrefill(cumulative_premium=None, surrender_value=None, withdrawal=0.0)

    def transfer_records_to_write(
        self,
        *,
        pair: tuple[MonthlyRecordModel, MonthlyRecordModel],
        holdings: list[HoldingModel],
    ) -> list[MonthlyRecordModel]:
        """從轉移的成對紀錄中濾掉走總成本推算的股票/ETF 端。

        股票/ETF 項目的當月淨投入改由總成本輸入方式推算（見 `derive`），轉移
        產生的淨投入不寫入，避免和推算值衝突；另一端照常寫入。兩端皆為股票/
        ETF 時回傳空清單，這是合法情況（畫面提示由呼叫端負責，非錯誤）。
        其餘端的轉移淨投入若需累加到既有月度紀錄，由 Repository 的
        `accumulate_net_investments` 處理，本方法只負責決定哪些列可寫。

        Args:
            pair: `build_transfer_pair` 產生的成對紀錄 (來源, 目標)。
            holdings: 涵蓋成對紀錄雙方項目的主檔清單（呼叫端保證雙方皆在清單內）。

        Returns:
            濾掉股票/ETF 端後的紀錄清單，依原順序排列，0～2 筆。
        """
        holdings_by_id = {holding.holding_id: holding for holding in holdings}
        return [
            record
            for record in pair
            if not self.uses_cost_basis(holding=holdings_by_id[record.holding_id])
        ]

    def _ensure_uses_cost_basis(self, *, holding: HoldingModel) -> None:
        """確保項目分類適用總成本推算，否則拋出例外，供各 public 方法共用守門。

        Args:
            holding: 項目主檔。

        Raises:
            DataValidationError: 項目分類不適用總成本推算時拋出。
        """
        if not self.uses_cost_basis(holding=holding):
            raise DataValidationError(
                f"項目「{holding.name}」分類不適用總成本推算，請改用市值/餘額與淨投入輸入"
            )

    def _ensure_uses_premium(self, *, holding: HoldingModel) -> None:
        """確保項目分類為保險，否則拋出例外。

        Args:
            holding: 項目主檔。

        Raises:
            DataValidationError: 項目分類不是保險時拋出。
        """
        if not self.uses_premium(holding=holding):
            raise DataValidationError(
                f"項目「{holding.name}」分類不適用累計保費推算，請改用對應的輸入方式"
            )

    def _ensure_uses_cost_chain(self, *, holding: HoldingModel) -> None:
        """確保項目分類屬於累計成本鏈（股票/ETF 或保險），否則拋出例外。

        Args:
            holding: 項目主檔。

        Raises:
            DataValidationError: 項目分類不是股票/ETF 或保險時拋出。
        """
        if not (self.uses_cost_basis(holding=holding) or self.uses_premium(holding=holding)):
            raise DataValidationError(
                f"項目「{holding.name}」分類不適用累計成本推算，請改用對應的輸入方式"
            )

    def _ensure_withdrawal_non_negative(self, *, withdrawal: float) -> None:
        """確保保險領回金額非負，否則拋出例外。

        Args:
            withdrawal: 本月領回金額。

        Raises:
            DataValidationError: 領回金額為負時拋出。
        """
        if withdrawal < 0:
            raise DataValidationError("領回金額不可為負")

    def _ensure_cash_dividend_non_negative(self, *, cash_dividend: float) -> None:
        """確保現金股利非負（入帳金額不會是負的），否則拋出例外。

        Args:
            cash_dividend: 本月現金股利。

        Raises:
            DataValidationError: 現金股利為負時拋出。
        """
        if cash_dividend < 0:
            raise DataValidationError("現金股利不可為負")

    def _recalculate_following(
        self,
        *,
        holding: HoldingModel,
        working_records: list[MonthlyRecordModel],
        cutoff_year_month: str,
    ) -> list[MonthlyRecordModel]:
        """往後掃描 cutoff 之後依時間順序排列的新制列，重算並回傳推算值有變的列。

        依時間順序處理是必要的：後面列的過渡規則加總可能涵蓋前面列剛更新的
        淨投入，所以每算完一筆就把更新結果寫回 working_records，讓下一筆用到
        最新狀態。舊制列（`total_cost` 為 None）不在掃描範圍內，永遠不被重算。

        Args:
            holding: 項目主檔。
            working_records: 已套用本次存檔／刪除異動的完整紀錄清單（會被原地更新）。
            cutoff_year_month: 異動的年月，只掃描晚於此年月的列。

        Returns:
            推算值和既存值不同（容許浮點誤差）的列，依年月排序。
        """
        forward_candidates = sorted(
            (
                record
                for record in working_records
                if record.year_month > cutoff_year_month and record.total_cost is not None
            ),
            key=lambda record: record.year_month,
        )

        changed: list[MonthlyRecordModel] = []
        for record in forward_candidates:
            derivation = self._derive_from_realized_income(
                holding=holding,
                records=working_records,
                year_month=record.year_month,
                total_cost=record.total_cost,
                realized_income=record.realized_income or 0.0,
            )
            if math.isclose(derivation.net_investment, record.net_investment, abs_tol=1e-6):
                continue

            updated_record = record.model_copy(update={"net_investment": derivation.net_investment})
            for idx, working_record in enumerate(working_records):
                if working_record.year_month == updated_record.year_month:
                    working_records[idx] = updated_record
                    break
            changed.append(updated_record)

        return changed
