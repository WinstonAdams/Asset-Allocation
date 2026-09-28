"""股票/ETF 依總成本與已實現收益推算月淨投入的核心運算（純運算，無 I/O、無 Streamlit）。"""

# ==== 原生（標準庫） ====
import math

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import NetInvestmentDerivation


class CostBasisService:
    """股票/ETF 總成本推算淨投入（純運算：無 I/O、無 Streamlit）。"""

    def __init__(self, *, cost_basis_categories: frozenset[str]) -> None:
        """初始化總成本推算服務。

        Args:
            cost_basis_categories: 走總成本推算的資產分類集合（由 bootstrap 注入）。
        """
        self.cost_basis_categories = cost_basis_categories

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
        realized_income: float,
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
            realized_income: 本月已實現收益（已實現損益＋現金股利，可為負）。

        Returns:
            前期總成本、是否為過渡期估算、推算出的本月淨投入。

        Raises:
            DataValidationError: 項目分類不適用總成本推算時拋出。
        """
        self._ensure_uses_cost_basis(holding=holding)

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
        realized_income: float,
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
            realized_income: 本月已實現收益（已實現損益＋現金股利，可為負）。

        Returns:
            [存檔列, *異動月份之後推算值有變的新制列]，依年月排序。

        Raises:
            DataValidationError: 項目分類不適用總成本推算時拋出。
        """
        derivation = self.derive(
            holding=holding,
            records=records,
            year_month=year_month,
            total_cost=total_cost,
            realized_income=realized_income,
        )
        saved_record = MonthlyRecordModel(
            holding_id=holding.holding_id,
            year_month=year_month,
            market_value=market_value,
            net_investment=derivation.net_investment,
            total_cost=total_cost,
            realized_income=realized_income,
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
            DataValidationError: 項目分類不適用總成本推算時拋出。
        """
        self._ensure_uses_cost_basis(holding=holding)

        working_records = [record for record in records if record.year_month != year_month]

        return self._recalculate_following(
            holding=holding, working_records=working_records, cutoff_year_month=year_month
        )

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
            derivation = self.derive(
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
