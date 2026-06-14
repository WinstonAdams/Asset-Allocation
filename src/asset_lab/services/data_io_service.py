"""CSV 匯出/匯入整形與驗證服務。

本服務為純整形運算，不碰 I/O、不依賴 Streamlit：把 model/DataFrame 轉成含表頭的標準
CSV 位元組（匯出），或把上傳的 CSV 位元組解析、驗證後還原成 model 清單（匯入）。實際的
批次寫入由上層委派 Repository。

匯入僅支援「還原到空庫」：目標庫是否為空屬 I/O 事實，由上層查詢後以 target_db_empty
布林旗標餵入，避免把 I/O 帶進本層；非空時拒絕整批，不覆蓋、不合併，以免污染既有資料。
所有驗證失敗一律轉成領域例外 DataValidationError，附友善中文訊息供上層直接呈現給使用者，
不讓底層解析堆疊噴到畫面。
"""

# ==== 原生（標準庫） ====
import io
import math

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, CSV_EXPORT, HOLDING_KIND
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.target import TargetAllocationModel


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    """把 DataFrame 輸出成含表頭、不含索引的 UTF-8 CSV 位元組。"""
    return df.to_csv(index=False).encode("utf-8")


def _optional_float(value: object) -> float | None:
    """把 CSV 讀回的數值正規化：空白（NaN）視為未填，回 None；否則回 float。"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


def _optional_str(value: object) -> str | None:
    """把 CSV 讀回的字串正規化：空白（NaN）視為未填，回 None；否則回 str。"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return str(value)


class DataIoService:
    """CSV 匯出/匯入整形與驗證（含表頭標準 CSV，三類資料各一份）。純整形，I/O 委派 Repository。"""

    def export_holdings_csv(self, *, holdings: list[HoldingModel]) -> bytes:
        """把主檔清單匯出成含表頭的 CSV 位元組（欄序固定，負債空欄留白）。"""
        rows = [
            {
                "holding_id": holding.holding_id,
                "name": holding.name,
                "kind": holding.kind,
                "category": holding.category,
                "initial_market_value": holding.initial_market_value,
                "initial_cost": holding.initial_cost,
            }
            for holding in holdings
        ]
        df = pd.DataFrame(rows, columns=list(CSV_EXPORT.HOLDINGS_COLUMNS))
        return _to_csv_bytes(df)

    def export_records_csv(self, *, records: pd.DataFrame) -> bytes:
        """把月度紀錄 DataFrame（Repository.read_all 產出）匯出成含表頭的 CSV 位元組。"""
        df = records.reindex(columns=list(CSV_EXPORT.RECORDS_COLUMNS))
        return _to_csv_bytes(df)

    def export_targets_csv(self, *, targets: list[TargetAllocationModel]) -> bytes:
        """把分類目標配置清單匯出成含表頭的 CSV 位元組。"""
        rows = [
            {"category": target.category, "target_weight": target.target_weight}
            for target in targets
        ]
        df = pd.DataFrame(rows, columns=list(CSV_EXPORT.TARGETS_COLUMNS))
        return _to_csv_bytes(df)

    def parse_and_validate(
        self,
        *,
        holdings_csv: bytes,
        records_csv: bytes,
        targets_csv: bytes,
        target_db_empty: bool,
    ) -> tuple[list[HoldingModel], list[MonthlyRecordModel], list[TargetAllocationModel]]:
        """解析三份 CSV、驗證後還原成 model 清單；任一驗證失敗則拒絕整批。

        驗證項目：目標庫須為空、三份表頭齊全、(holding_id, year_month) 唯一鍵不重複、
        性質與資產分類合法、月度紀錄須掛在主檔存在的項目上。

        Args:
            holdings_csv: 主檔 CSV 位元組（含表頭）。
            records_csv: 月度紀錄 CSV 位元組（含表頭）。
            targets_csv: 分類目標配置 CSV 位元組（含表頭）。
            target_db_empty: 目標庫是否為空（由上層查詢 Repository 後傳入；本層不做 I/O）。

        Returns:
            (主檔清單, 月度紀錄清單, 目標配置清單)，可直接交 Repository 批次寫入空庫。

        Raises:
            DataValidationError: 任一驗證失敗（附友善中文訊息供上層呈現）。
        """
        # 僅支援還原到空庫：非空時拒絕整批，不覆蓋也不合併，以免污染既有資料
        if not target_db_empty:
            raise DataValidationError(
                "目標資料庫不是空的；匯入僅支援還原到空庫，請先清空資料庫再匯入。"
            )

        holdings_df = self._read_csv(label="持有項目主檔", raw=holdings_csv)
        records_df = self._read_csv(label="月度紀錄", raw=records_csv)
        targets_df = self._read_csv(label="分類目標配置", raw=targets_csv)

        self._require_headers(
            label="持有項目主檔", df=holdings_df, expected=CSV_EXPORT.HOLDINGS_COLUMNS
        )
        self._require_headers(
            label="月度紀錄", df=records_df, expected=CSV_EXPORT.RECORDS_COLUMNS
        )
        self._require_headers(
            label="分類目標配置", df=targets_df, expected=CSV_EXPORT.TARGETS_COLUMNS
        )

        holdings = self._build_holdings(holdings_df)
        records = self._build_records(records_df)
        targets = self._build_targets(targets_df)

        self._reject_dangling_records(holdings=holdings, records=records)
        return holdings, records, targets

    @staticmethod
    def _read_csv(*, label: str, raw: bytes) -> pd.DataFrame:
        """把 CSV 位元組讀成 DataFrame；解析失敗轉成友善領域例外，不外漏底層堆疊。"""
        try:
            return pd.read_csv(io.BytesIO(raw))
        except Exception as error:
            raise DataValidationError(f"{label} CSV 無法解析，請確認檔案格式正確。") from error

    @staticmethod
    def _require_headers(*, label: str, df: pd.DataFrame, expected: tuple[str, ...]) -> None:
        """確認必要表頭欄位齊全；缺漏則拒絕並點名缺哪些欄位。"""
        missing = [column for column in expected if column not in df.columns]
        if missing:
            raise DataValidationError(
                f"{label} CSV 表頭缺少必要欄位：{', '.join(missing)}。"
            )

    @staticmethod
    def _build_holdings(df: pd.DataFrame) -> list[HoldingModel]:
        """逐列還原主檔並驗證性質與分類合法；空欄正規化為 None。"""
        holdings: list[HoldingModel] = []
        for row in df.to_dict(orient="records"):
            kind = _optional_str(row["kind"])
            if kind not in HOLDING_KIND.ALL:
                raise DataValidationError(
                    f"持有項目性質非法：{kind}（僅允許資產或負債）。"
                )
            category = _optional_str(row["category"])
            # 資產分類必須落在受控清單；負債不歸類（分類留空合法）
            if (
                kind == HOLDING_KIND.ASSET
                and category is not None
                and category not in ASSET_CATEGORIES.ALL
            ):
                raise DataValidationError(f"資產分類非法：{category}（不在受控清單內）。")
            holdings.append(
                HoldingModel(
                    holding_id=int(row["holding_id"]),
                    name=str(row["name"]),
                    kind=kind,
                    category=category,
                    initial_market_value=_optional_float(row["initial_market_value"]),
                    initial_cost=_optional_float(row["initial_cost"]),
                )
            )
        return holdings

    @staticmethod
    def _build_records(df: pd.DataFrame) -> list[MonthlyRecordModel]:
        """逐列還原月度紀錄並驗證 (holding_id, year_month) 唯一鍵不重複。"""
        records: list[MonthlyRecordModel] = []
        seen: set[tuple[int, str]] = set()
        for row in df.to_dict(orient="records"):
            holding_id = int(row["holding_id"])
            year_month = str(row["year_month"])
            key = (holding_id, year_month)
            if key in seen:
                raise DataValidationError(
                    f"月度紀錄有重複的項目與年月：(項目 {holding_id}, {year_month})。"
                )
            seen.add(key)
            records.append(
                MonthlyRecordModel(
                    holding_id=holding_id,
                    year_month=year_month,
                    market_value=_optional_float(row["market_value"]),
                    net_investment=_optional_float(row["net_investment"]) or 0.0,
                )
            )
        return records

    @staticmethod
    def _build_targets(df: pd.DataFrame) -> list[TargetAllocationModel]:
        """逐列還原分類目標配置。"""
        return [
            TargetAllocationModel(
                category=str(row["category"]),
                target_weight=float(row["target_weight"]),
            )
            for row in df.to_dict(orient="records")
        ]

    @staticmethod
    def _reject_dangling_records(
        *, holdings: list[HoldingModel], records: list[MonthlyRecordModel]
    ) -> None:
        """拒絕掛在主檔不存在項目上的孤兒紀錄（資料一致性，避免污染）。"""
        known_ids = {holding.holding_id for holding in holdings}
        for record in records:
            if record.holding_id not in known_ids:
                raise DataValidationError(
                    f"月度紀錄掛在主檔不存在的項目上：項目 {record.holding_id}。"
                )
