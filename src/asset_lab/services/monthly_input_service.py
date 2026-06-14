"""月度錄入業務邏輯——帶入上月仍持有清單與項目間成對轉移的純運算服務。

本服務為純運算，不碰 I/O、不依賴 Streamlit；實際寫入由 Page 委派 Repository 執行。
建構子注入兩個記錄/主檔讀取層，僅用於「讀取上月紀錄」與「首月挑主檔」，本服務
不在內部觸發任何寫入。

帶入語意：新增一個月份時，自動帶入「最新有資料月」中仍持有的項目
作為待輸入清單；市值欄留空待使用者輸入，淨投入欄一律從 0 起算（不沿用上月淨投入，
避免把上月的資金流動誤帶到新月份）。已賣出（出清當月記市值 0、之後缺列）的項目視為
不再持有，不帶入；負債與資產一視同仁，只要仍持有（未出清）就帶入。最新有資料月不存在
（首月）時改由主檔提供待挑選項目。

轉移語意（項目間轉移）：把一筆金額由來源項目移到目標項目，於同一月份成對記錄——來源記
−amount、目標記 +amount。成對淨投入合計為 0，故整體層級的總資產與報酬率不因轉移而變動
（資金只是在資產間移動）。
"""

# ==== 原生（標準庫） ====
from typing import Protocol

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel

# 出清語意：賣出當月記市值 0，視為已不再持有，後續月份不帶入
_SOLD_OUT_MARKET_VALUE = 0.0

# 帶入新月份時，市值留空待輸入、淨投入一律從 0 起算（不沿用上月）。
_PREFILL_NET_INVESTMENT = 0.0


class _RecordReader(Protocol):
    """帶入邏輯所需的記錄讀取介面（由 RecordRepository 實作）。"""

    def latest_year_month(self) -> str | None: ...

    def read_month(self, *, year_month: str) -> list[MonthlyRecordModel]: ...


class _HoldingReader(Protocol):
    """首月挑選所需的主檔讀取介面（由 HoldingRepository 實作）。"""

    def list_holdings(self) -> list[HoldingModel]: ...


class MonthlyInputService:
    """月度錄入：帶入上月仍持有清單、產生項目間成對轉移紀錄。純運算層。"""

    def __init__(self, *, holding_repo: _HoldingReader, record_repo: _RecordReader) -> None:
        """初始化月度錄入服務。

        Args:
            holding_repo: 主檔讀取層，首月無上月可帶時用於列出待挑選項目。
            record_repo: 記錄讀取層，用於取得最新有資料月與該月各項目紀錄。
        """
        self._holding_repo = holding_repo
        self._record_repo = record_repo

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

    def build_transfer_pair(
        self, *, source_id: int, dest_id: int, amount: float, year_month: str
    ) -> tuple[MonthlyRecordModel, MonthlyRecordModel]:
        """產生項目間轉移的成對紀錄：來源記 −amount、目標記 +amount。

        兩筆掛在同一月份、金額相等方向相反，淨投入合計為 0，故整體總資產與報酬率
        不因轉移而變動。僅產生紀錄物件，實際寫入由 Page 委派 Repository 執行。

        轉移輸入須通過防呆：金額必須為正數，且來源與目標必須是不同項目；違反任一
        條件即拒絕並拋例外，不產生任何紀錄。金額非正代表無資金移動或方向不明，
        來源等於目標代表自己轉給自己（淨效果為 0、形同未轉移），皆視為無效輸入。

        Args:
            source_id: 轉出來源項目的 holding_id。
            dest_id: 轉入目標項目的 holding_id。
            amount: 轉移金額，須為正數。
            year_month: 轉移發生的月份，'YYYY-MM' 格式。

        Returns:
            (來源紀錄, 目標紀錄) 二元組；來源淨投入為 −amount、目標為 +amount，
            兩筆市值皆留空（市值更新另行輸入）。

        Raises:
            DataValidationError: 金額非正（≤ 0），或來源與目標為同一項目。
        """
        if amount <= 0:
            raise DataValidationError(f"轉移金額須為正數，收到：{amount!r}")
        if source_id == dest_id:
            raise DataValidationError(f"轉移的來源與目標不可為同一項目：{source_id!r}")
        source = MonthlyRecordModel(
            holding_id=source_id, year_month=year_month, net_investment=-amount
        )
        dest = MonthlyRecordModel(
            holding_id=dest_id, year_month=year_month, net_investment=amount
        )
        return source, dest

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
