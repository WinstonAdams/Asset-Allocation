"""股票/ETF 依總成本與已實現收益推算月淨投入的核心運算（純運算，無 I/O、無 Streamlit）。"""

# ==== 原生（標準庫） ====
# 無

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
        if not self.uses_cost_basis(holding=holding):
            raise DataValidationError(
                f"項目「{holding.name}」分類不適用總成本推算，請改用市值/餘額與淨投入輸入"
            )

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
