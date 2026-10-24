"""月度錄入業務邏輯——帶入上月仍持有清單、錄入方式解析與負債應繳金額紀錄的純運算服務。

本服務為純運算，不碰 I/O、不依賴 Streamlit；實際寫入由 Page 委派 Repository 執行。
建構子注入兩個記錄/主檔讀取層，僅用於「讀取上月紀錄」與「首月挑主檔」，本服務
不在內部觸發任何寫入。

帶入語意：新增一個月份時，自動帶入「最新有資料月」中仍持有的項目
作為待輸入清單；市值欄留空待使用者輸入，淨投入欄一律從 0 起算（不沿用上月淨投入，
避免把上月的資金流動誤帶到新月份）。已賣出（出清當月記市值 0、之後缺列）的項目視為
不再持有，不帶入；負債與資產一視同仁，只要仍持有（未出清）就帶入。最新有資料月不存在
（首月）時改由主檔提供待挑選項目。

錄入方式：負債一律只填應繳金額（淨投入固定 0）；資產依分類決定填總成本、累計保費
或餘額，分類未指定者拒絕錄入。
"""

# ==== 原生（標準庫） ====
from collections.abc import Mapping
from typing import Protocol

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import MonthRecordRow, RecordEditorPrefill

# 出清語意：賣出當月記市值 0，視為已不再持有，後續月份不帶入
_SOLD_OUT_MARKET_VALUE = 0.0

# 帶入新月份時，市值留空待輸入、淨投入一律從 0 起算（不沿用上月）。
_PREFILL_NET_INVESTMENT = 0.0

# 負債不計入報酬率，月淨投入固定為 0。
_LIABILITY_NET_INVESTMENT = 0.0


class _RecordReader(Protocol):
    """帶入邏輯所需的記錄讀取介面（由 RecordRepository 實作）。"""

    def latest_year_month(self) -> str | None: ...

    def read_month(self, *, year_month: str) -> list[MonthlyRecordModel]: ...


class _HoldingReader(Protocol):
    """首月挑選所需的主檔讀取介面（由 HoldingRepository 實作）。"""

    def list_holdings(self) -> list[HoldingModel]: ...


class MonthlyInputService:
    """月度錄入：帶入上月仍持有清單、解析錄入方式、產生負債應繳金額紀錄。純運算層。"""

    def __init__(
        self,
        *,
        holding_repo: _HoldingReader,
        record_repo: _RecordReader,
        input_mode_by_category: Mapping[str, str],
        liability_kind: str,
        liability_input_mode: str,
    ) -> None:
        """初始化月度錄入服務。

        Args:
            holding_repo: 主檔讀取層，首月無上月可帶時用於列出待挑選項目。
            record_repo: 記錄讀取層，用於取得最新有資料月與該月各項目紀錄。
            input_mode_by_category: 資產分類對應錄入方式代碼的對照表。
            liability_kind: 負債的項目性質代碼。
            liability_input_mode: 負債一律採用的錄入方式代碼。
        """
        self._holding_repo = holding_repo
        self._record_repo = record_repo
        self._input_mode_by_category = input_mode_by_category
        self._liability_kind = liability_kind
        self._liability_input_mode = liability_input_mode

    def resolve_input_mode(self, *, holding: HoldingModel) -> str:
        """依項目性質與分類決定月度錄入方式。

        負債一律採應繳金額錄入；資產依分類對照表決定。資產分類留空或不在對照表內
        （例如匯入檔帶入未分類項目）時拒絕，不默默當成某一種方式處理，避免推算錯誤。

        Args:
            holding: 要錄入的項目主檔。

        Returns:
            錄入方式代碼。

        Raises:
            DataValidationError: 資產項目分類未指定或沒有對應的錄入方式。
        """
        if holding.kind == self._liability_kind:
            return self._liability_input_mode
        mode = self._input_mode_by_category.get(holding.category) if holding.category else None
        if mode is None:
            raise DataValidationError(f"項目「{holding.name}」尚未指定分類，請先到設定頁指定分類")
        return mode

    def build_amount_due_record(
        self, *, holding: HoldingModel, year_month: str, amount_due: float
    ) -> MonthlyRecordModel:
        """產生負債的月度紀錄：金額為應繳金額，淨投入固定為 0。

        負債不計入報酬率，淨投入沒有業務意義，故不開放手填。

        Args:
            holding: 負債項目主檔。
            year_month: 紀錄月份，'YYYY-MM' 格式。
            amount_due: 本月應繳金額。

        Returns:
            待寫入的紀錄；成本相關欄位皆為 None。

        Raises:
            DataValidationError: 項目不是負債，或尚未建立（無 holding_id）。
        """
        if holding.kind != self._liability_kind:
            raise DataValidationError(f"項目「{holding.name}」不是負債，無法以應繳金額錄入")
        if holding.holding_id is None:
            raise DataValidationError(f"項目「{holding.name}」尚未建立，無法存檔")
        return MonthlyRecordModel(
            holding_id=holding.holding_id,
            year_month=year_month,
            market_value=amount_due,
            net_investment=_LIABILITY_NET_INVESTMENT,
        )

    def prefill_from_previous(self, *, target_ym: str) -> list[MonthlyRecordModel]:
        """帶入最新有資料月仍持有的項目，組成新月份的待輸入清單。

        以最新有資料月為帶入來源：該月仍持有（未出清）的每個項目都帶入目標月份，
        市值欄留空待輸入、淨投入欄從 0 起算。已賣出（市值 0）的項目不帶入。
        最新有資料月不存在時（首月）改由主檔列出所有項目作為待挑選清單。

        Args:
            target_ym: 欲新增的目標月份，'YYYY-MM' 格式；帶入的紀錄皆掛在此月份。

        Returns:
            目標月份的待輸入 MonthlyRecordModel 清單，市值為 None、淨投入為 0；
            無上月且主檔為空，或上月項目全數已賣出時，為空清單。
        """
        previous_ym = self._record_repo.latest_year_month()
        if previous_ym is None:
            return self._prefill_from_holdings(target_ym=target_ym)

        previous_records = self._record_repo.read_month(year_month=previous_ym)
        return [
            self._blank_record(holding_id=record.holding_id, target_ym=target_ym)
            for record in previous_records
            if self._still_held(record)
        ]

    def build_record_prefill(
        self, *, records: list[MonthlyRecordModel], holding_id: int, year_month: str
    ) -> RecordEditorPrefill:
        """算出餘額與應繳金額錄入框的帶入值：該月已有紀錄就照存的值，沒有則為現行預設。

        已存的市值為空白（None）時保持空白；該月無紀錄時市值同樣留空，
        避免使用者沒改就存檔而把餘額存成 0。

        Args:
            records: 已讀好的紀錄清單（通常為當月全部紀錄）。
            holding_id: 選取的項目。
            year_month: 選取的月份，'YYYY-MM' 格式。

        Returns:
            帶入值；無相符紀錄時市值留空（None）、淨投入為 0。
        """
        for record in records:
            if record.holding_id == holding_id and record.year_month == year_month:
                return RecordEditorPrefill(
                    market_value=record.market_value,
                    net_investment=record.net_investment,
                )
        return RecordEditorPrefill(market_value=None, net_investment=0.0)

    def summarize_month(
        self, *, records: list[MonthlyRecordModel], holdings: list[HoldingModel]
    ) -> list[MonthRecordRow]:
        """把本月已存紀錄組成唯讀表格列，標記金額未填的列與負債列。

        提醒只看金額（市值、餘額或負債應繳金額）是否空白，不分項目分類。項目名稱由主檔對應；項目不可刪除且匯入
        會拒絕孤兒紀錄，故主檔必定涵蓋所有紀錄的項目。

        Args:
            records: 當月紀錄，輸出依此順序一筆一列。
            holdings: 項目主檔，用於對應名稱。

        Returns:
            與 records 同順序的表格列；無紀錄時為空清單。
        """
        holdings_by_id = {holding.holding_id: holding for holding in holdings}
        return [
            MonthRecordRow(
                holding_id=record.holding_id,
                name=holdings_by_id[record.holding_id].name,
                market_value=record.market_value,
                net_investment=record.net_investment,
                total_cost=record.total_cost,
                realized_income=record.realized_income,
                market_value_missing=record.market_value is None,
                is_liability=holdings_by_id[record.holding_id].kind == self._liability_kind,
            )
            for record in records
        ]

    def _prefill_from_holdings(self, *, target_ym: str) -> list[MonthlyRecordModel]:
        """首月無上月可帶：由主檔列出所有項目作為待輸入清單。"""
        return [
            self._blank_record(holding_id=holding.holding_id, target_ym=target_ym)
            for holding in self._holding_repo.list_holdings()
        ]

    @staticmethod
    def _still_held(record: MonthlyRecordModel) -> bool:
        """判斷上月某項目是否仍持有：市值 0 為出清語意，視為已不持有。"""
        return record.market_value != _SOLD_OUT_MARKET_VALUE

    @staticmethod
    def _blank_record(*, holding_id: int, target_ym: str) -> MonthlyRecordModel:
        """產生一筆待輸入紀錄：市值留空、淨投入從 0 起算。"""
        return MonthlyRecordModel(
            holding_id=holding_id,
            year_month=target_ym,
            market_value=None,
            net_investment=_PREFILL_NET_INVESTMENT,
        )
