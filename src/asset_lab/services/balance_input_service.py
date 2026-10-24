"""活存/定存以餘額變動推算月淨投入（純運算：無 I/O、無 Streamlit）。"""

# ==== 原生（標準庫） ====
import math

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import BalanceDerivation

# 浮點比較容差，與 CostBasisService 連動重算一致
_ABS_TOL = 1e-6


class BalanceInputService:
    """活存/定存餘額推算淨投入，以及修改/刪除時下一筆的連動重算。"""

    def __init__(self, *, balance_categories: frozenset[str]) -> None:
        """初始化餘額推算服務。

        Args:
            balance_categories: 走餘額推算的資產分類集合（由 bootstrap 注入）。
        """
        self.balance_categories = balance_categories

    def derive(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
        balance: float,
    ) -> BalanceDerivation:
        """推算項目當月淨投入＝本月餘額 − 前期餘額。

        前期餘額取年月早於 year_month、最近一筆餘額不為 None 的紀錄；餘額空白的列
        （例如過去項目間轉移留下的只有淨投入的列）跳過；都沒有則取主檔初始市值
        （None 當 0）。

        Args:
            holding: 項目主檔，須為走餘額推算的分類。
            records: 該項目的全部月度紀錄（呼叫端保證只含該項目、任意順序）。
            year_month: 本次要推算的年月（'YYYY-MM'）。
            balance: 本月使用者輸入的餘額。

        Returns:
            前期餘額與推算出的本月淨投入。

        Raises:
            DataValidationError: 項目分類不適用餘額推算時拋出。
        """
        self._ensure_balance_category(holding=holding)
        previous = self._previous_balance(holding=holding, records=records, year_month=year_month)
        return BalanceDerivation(previous_balance=previous, net_investment=balance - previous)

    def plan_save(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
        balance: float,
    ) -> list[MonthlyRecordModel]:
        """規劃存檔要寫入的列：本月列，加上前期餘額因此改變的下一筆有餘額列。

        Args:
            holding: 項目主檔，須為走餘額推算的分類。
            records: 該項目的全部月度紀錄（不含本次異動）。
            year_month: 本次存檔的年月。
            balance: 本月使用者輸入的餘額。

        Returns:
            本月列在前；下一筆列只在其前期餘額改變且重算值與既存值不同時附上。

        Raises:
            DataValidationError: 項目分類不適用餘額推算時拋出。
        """
        derivation = self.derive(
            holding=holding, records=records, year_month=year_month, balance=balance
        )
        saved = MonthlyRecordModel(
            holding_id=self._holding_id(holding=holding),
            year_month=year_month,
            market_value=balance,
            net_investment=derivation.net_investment,
        )
        after = [r for r in records if r.year_month != year_month] + [saved]
        planned = [saved]
        planned.extend(
            self._recalculate_next(
                holding=holding, before=records, after=after, year_month=year_month
            )
        )
        return planned

    def plan_delete(
        self,
        *,
        holding: HoldingModel,
        records: list[MonthlyRecordModel],
        year_month: str,
    ) -> list[MonthlyRecordModel]:
        """規劃刪除某月後要重寫的列：前期餘額因此改變的下一筆有餘額列。

        Args:
            holding: 項目主檔，須為走餘額推算的分類。
            records: 該項目的全部月度紀錄（含要刪除的那筆）。
            year_month: 要刪除的年月。

        Returns:
            需重寫的下一筆列；無需重算時為空清單。

        Raises:
            DataValidationError: 項目分類不適用餘額推算時拋出。
        """
        self._ensure_balance_category(holding=holding)
        after = [r for r in records if r.year_month != year_month]
        return self._recalculate_next(
            holding=holding, before=records, after=after, year_month=year_month
        )

    def _ensure_balance_category(self, *, holding: HoldingModel) -> None:
        if holding.category not in self.balance_categories:
            raise DataValidationError(f"項目「{holding.name}」的分類不適用餘額推算")

    @staticmethod
    def _holding_id(*, holding: HoldingModel) -> int:
        if holding.holding_id is None:
            raise DataValidationError(f"項目「{holding.name}」尚未建立，無法存檔")
        return holding.holding_id

    @staticmethod
    def _previous_balance(
        *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str
    ) -> float:
        """年月早於 year_month、最近一筆有餘額的值；沒有則取初始市值（None 當 0）。

        Returns:
            前期餘額。
        """
        earlier = [r for r in records if r.year_month < year_month and r.market_value is not None]
        if earlier:
            latest = max(earlier, key=lambda r: r.year_month)
            return float(latest.market_value)  # type: ignore[arg-type]
        return holding.initial_market_value or 0.0

    def _recalculate_next(
        self,
        *,
        holding: HoldingModel,
        before: list[MonthlyRecordModel],
        after: list[MonthlyRecordModel],
        year_month: str,
    ) -> list[MonthlyRecordModel]:
        """異動後，晚於 year_month 第一筆有餘額列的前期餘額若改變就重算它。

        Returns:
            需重寫的下一筆列；無需重算時為空清單。
        """
        following = sorted(
            (r for r in after if r.year_month > year_month and r.market_value is not None),
            key=lambda r: r.year_month,
        )
        if not following:
            return []
        target = following[0]

        previous_before = self._previous_balance(
            holding=holding, records=before, year_month=target.year_month
        )
        previous_after = self._previous_balance(
            holding=holding, records=after, year_month=target.year_month
        )
        if math.isclose(previous_before, previous_after, abs_tol=_ABS_TOL):
            return []

        net_investment = float(target.market_value) - previous_after  # type: ignore[arg-type]
        if math.isclose(net_investment, target.net_investment, abs_tol=_ABS_TOL):
            return []
        return [target.model_copy(update={"net_investment": net_investment})]
