# ==== 原生（標準庫） ====
import io
from pathlib import Path
from types import SimpleNamespace

# ==== 第三方套件 ====
import libsql
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND, HOLDING_PURPOSE
from asset_lab.core.exceptions import DataValidationError, PersistenceError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.target import TargetAllocationModel
from asset_lab.repositories.csv_import_writer import write_import
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.repositories.transaction_repository import TransactionRepository
from asset_lab.services.data_io_service import DataIoService

APP_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def service() -> DataIoService:
    return DataIoService()


def _holdings() -> list[HoldingModel]:
    """一份含資產與負債的主檔（負債無分類/初始值）。"""
    return [
        HoldingModel(
            holding_id=1,
            name="台積電",
            kind=HOLDING_KIND.ASSET,
            category=ASSET_CATEGORIES.TW_STOCK,
            initial_market_value=500000.0,
            initial_cost=300000.0,
        ),
        HoldingModel(
            holding_id=2,
            name="房貸",
            kind=HOLDING_KIND.LIABILITY,
            category=None,
            initial_market_value=None,
            initial_cost=None,
        ),
    ]


def _records_df() -> pd.DataFrame:
    """主檔對應的月度紀錄（市值/淨投入/總成本/已實現收益、負債餘額），欄序同 read_all。

    holding_id=1 的第一筆為新制股票/ETF 列（total_cost/realized_income/cash_dividend 皆有值）；
    其餘列非股票/ETF 或舊制，這三欄皆未填（None）。
    """
    return pd.DataFrame(
        [
            (1, "2026-01", 510000.0, 0.0, 300000.0, 5000.0, 1200.0),
            (1, "2026-02", 0.0, -520000.0, None, None, None),
            (2, "2026-01", 800000.0, 0.0, None, None, None),
        ],
        columns=[
            "holding_id",
            "year_month",
            "market_value",
            "net_investment",
            "total_cost",
            "realized_income",
            "cash_dividend",
        ],
    )


def _targets() -> list[TargetAllocationModel]:
    """一份各分類目標配置（總和 100%）。"""
    return [
        TargetAllocationModel(category=ASSET_CATEGORIES.TW_STOCK, target_weight=60.0),
        TargetAllocationModel(category=ASSET_CATEGORIES.DEMAND_DEPOSIT, target_weight=40.0),
    ]


def _read_csv_bytes(csv_bytes: bytes) -> pd.DataFrame:
    """把含表頭的 CSV 位元組讀回 DataFrame（測試端用來檢視匯出內容）。"""
    return pd.read_csv(io.BytesIO(csv_bytes))


class TestExportImportRoundTrip:
    """SC-031：匯出 CSV 含完整紀錄並可匯入空庫還原一致。"""

    @pytest.mark.scenario("SC-031")
    def test_sc031_export_holdings_has_header_and_full_records(self, service):
        # 匯出主檔 CSV：第一列為表頭，含全部項目（資產與負債）與其性質/初始市值/初始成本/分類/用途
        csv_bytes = service.export_holdings_csv(holdings=_holdings())
        df = _read_csv_bytes(csv_bytes)
        assert list(df.columns) == [
            "holding_id",
            "name",
            "kind",
            "category",
            "initial_market_value",
            "initial_cost",
            "purpose",
        ]
        assert list(df["holding_id"]) == [1, 2]
        assert list(df["name"]) == ["台積電", "房貸"]
        assert list(df["kind"]) == [HOLDING_KIND.ASSET, HOLDING_KIND.LIABILITY]

    @pytest.mark.scenario("SC-031")
    def test_sc031_export_records_has_header_and_all_rows(self, service):
        # 匯出月度紀錄 CSV：含表頭與全部月度列（資產市值/淨投入/總成本/已實現收益、負債餘額）
        csv_bytes = service.export_records_csv(records=_records_df())
        df = _read_csv_bytes(csv_bytes)
        assert list(df.columns) == [
            "holding_id",
            "year_month",
            "market_value",
            "net_investment",
            "total_cost",
            "realized_income",
            "cash_dividend",
        ]
        assert len(df) == 3
        assert df["total_cost"].iloc[0] == 300000.0
        assert df["realized_income"].iloc[0] == 5000.0
        assert df["cash_dividend"].iloc[0] == 1200.0

    @pytest.mark.scenario("SC-031")
    def test_sc031_export_targets_has_header_and_all_rows(self, service):
        # 匯出目標配置 CSV：含表頭與各分類目標比重
        csv_bytes = service.export_targets_csv(targets=_targets())
        df = _read_csv_bytes(csv_bytes)
        assert list(df.columns) == ["category", "target_weight"]
        assert dict(zip(df["category"], df["target_weight"], strict=True)) == {
            ASSET_CATEGORIES.TW_STOCK: 60.0,
            ASSET_CATEGORIES.DEMAND_DEPOSIT: 40.0,
        }

    @pytest.mark.scenario("SC-031")
    def test_sc031_roundtrip_restores_identical_data_into_empty_db(self, service):
        # 匯出後再解析（匯入空庫），主檔/紀錄/目標皆與匯出前一致
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        records_csv = service.export_records_csv(records=_records_df())
        targets_csv = service.export_targets_csv(targets=_targets())

        holdings, records, targets = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=records_csv,
            targets_csv=targets_csv,
            target_db_empty=True,
        )

        assert holdings == _holdings()
        assert targets == _targets()
        expected_records = [
            MonthlyRecordModel(
                holding_id=1,
                year_month="2026-01",
                market_value=510000.0,
                net_investment=0.0,
                total_cost=300000.0,
                realized_income=5000.0,
                cash_dividend=1200.0,
            ),
            MonthlyRecordModel(
                holding_id=1, year_month="2026-02", market_value=0.0, net_investment=-520000.0
            ),
            MonthlyRecordModel(
                holding_id=2, year_month="2026-01", market_value=800000.0, net_investment=0.0
            ),
        ]
        assert records == expected_records

    @pytest.mark.scenario("SC-031")
    def test_sc031_liability_nulls_survive_roundtrip(self, service):
        # 負債的分類/初始市值/初始成本為空，round-trip 後仍為 None（不被誤填成 0 或空字串）
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        records_csv = service.export_records_csv(records=_records_df())
        targets_csv = service.export_targets_csv(targets=_targets())

        holdings, _, _ = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=records_csv,
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        liability = next(h for h in holdings if h.kind == HOLDING_KIND.LIABILITY)
        assert liability.category is None
        assert liability.initial_market_value is None
        assert liability.initial_cost is None

    @pytest.mark.scenario("SC-031")
    def test_sc031_empty_dataset_roundtrips_to_empty(self, service):
        # 全空資料集（僅表頭）匯出再匯入空庫，還原為三份空清單
        holdings_csv = service.export_holdings_csv(holdings=[])
        records_csv = service.export_records_csv(
            records=pd.DataFrame(
                columns=["holding_id", "year_month", "market_value", "net_investment"]
            )
        )
        targets_csv = service.export_targets_csv(targets=[])

        holdings, records, targets = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=records_csv,
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        assert holdings == []
        assert records == []
        assert targets == []


class TestImportValidationRejectsBadData:
    """SC-032：匯入 CSV 須驗證格式與唯一鍵避免污染。"""

    def _valid_csvs(self, service) -> tuple[bytes, bytes, bytes]:
        return (
            service.export_holdings_csv(holdings=_holdings()),
            service.export_records_csv(records=_records_df()),
            service.export_targets_csv(targets=_targets()),
        )

    @pytest.mark.scenario("SC-032")
    def test_sc032_missing_holdings_header_is_rejected(self, service):
        # 主檔 CSV 缺少必要欄位（缺 kind）→ 拒絕匯入，訊息點名缺漏欄位
        _, records_csv, targets_csv = self._valid_csvs(service)
        broken = b"holding_id,name,category,initial_market_value,initial_cost\n1,X,tw,1,1\n"
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=broken,
                records_csv=records_csv,
                targets_csv=targets_csv,
                target_db_empty=True,
            )
        assert "kind" in str(exc.value)

    @pytest.mark.scenario("SC-032")
    def test_sc032_missing_records_header_is_rejected(self, service):
        # 月度紀錄 CSV 缺少必要欄位（缺 year_month）→ 拒絕匯入
        holdings_csv, _, targets_csv = self._valid_csvs(service)
        broken = b"holding_id,market_value,net_investment\n1,1,0\n"
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=holdings_csv,
                records_csv=broken,
                targets_csv=targets_csv,
                target_db_empty=True,
            )
        assert "year_month" in str(exc.value)

    @pytest.mark.scenario("SC-032")
    def test_sc032_missing_targets_header_is_rejected(self, service):
        # 目標配置 CSV 缺少必要欄位（缺 target_weight）→ 拒絕匯入
        holdings_csv, records_csv, _ = self._valid_csvs(service)
        broken = b"category\ntw\n"
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=holdings_csv,
                records_csv=records_csv,
                targets_csv=broken,
                target_db_empty=True,
            )
        assert "target_weight" in str(exc.value)

    @pytest.mark.scenario("SC-032")
    def test_sc032_duplicate_record_key_is_rejected(self, service):
        # 月度紀錄含重複 (holding_id, year_month) → 拒絕匯入，避免同月同項目兩列污染
        holdings_csv, _, targets_csv = self._valid_csvs(service)
        dup = (
            b"holding_id,year_month,market_value,net_investment\n"
            b"1,2026-01,510000.0,0.0\n"
            b"1,2026-01,999999.0,0.0\n"
        )
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=holdings_csv,
                records_csv=dup,
                targets_csv=targets_csv,
                target_db_empty=True,
            )
        assert "2026-01" in str(exc.value)

    @pytest.mark.scenario("SC-032")
    def test_sc032_invalid_kind_is_rejected(self, service):
        # 主檔含非法性質（既非資產也非負債）→ 拒絕匯入
        _, records_csv, targets_csv = self._valid_csvs(service)
        bad_kind = (
            b"holding_id,name,kind,category,initial_market_value,initial_cost\n"
            b"1,X,crypto,,,\n"
        )
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=bad_kind,
                records_csv=records_csv,
                targets_csv=targets_csv,
                target_db_empty=True,
            )
        assert "crypto" in str(exc.value)

    @pytest.mark.scenario("SC-032")
    def test_sc032_invalid_asset_category_is_rejected(self, service):
        # 資產項目的分類不在受控清單 → 拒絕匯入
        _, records_csv, targets_csv = self._valid_csvs(service)
        bad_cat = (
            b"holding_id,name,kind,category,initial_market_value,initial_cost\n"
            b"1,X,asset,\xe5\x8a\xa0\xe5\xaf\x86\xe8\xb2\xa8\xe5\xb9\xa3,1,1\n"
        )
        with pytest.raises(DataValidationError):
            service.parse_and_validate(
                holdings_csv=bad_cat,
                records_csv=records_csv,
                targets_csv=targets_csv,
                target_db_empty=True,
            )

    @pytest.mark.scenario("SC-032")
    def test_sc032_non_empty_target_db_is_rejected_with_clear_message(self, service):
        # 目標庫非空 → 拒絕匯入並提示先清空（不覆蓋、不合併；僅支援還原到空庫）
        holdings_csv, records_csv, targets_csv = self._valid_csvs(service)
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=holdings_csv,
                records_csv=records_csv,
                targets_csv=targets_csv,
                target_db_empty=False,
            )
        assert "清空" in str(exc.value)

    @pytest.mark.scenario("SC-032")
    def test_sc032_rejection_uses_friendly_domain_error_not_technical_trace(self, service):
        # 驗證失敗一律以領域例外 DataValidationError 表達（友善訊息，非底層解析堆疊）
        holdings_csv, _, targets_csv = self._valid_csvs(service)
        broken = b"holding_id,market_value,net_investment\n1,1,0\n"
        with pytest.raises(DataValidationError):
            service.parse_and_validate(
                holdings_csv=holdings_csv,
                records_csv=broken,
                targets_csv=targets_csv,
                target_db_empty=True,
            )


def _empty_records_csv(service: DataIoService) -> bytes:
    """一份僅含表頭、無資料列的月度紀錄 CSV（測試用，聚焦持有項目主檔行為）。"""
    return service.export_records_csv(
        records=pd.DataFrame(
            columns=["holding_id", "year_month", "market_value", "net_investment"]
        )
    )


def _legacy_holdings_csv_bytes() -> bytes:
    """模擬本 Change 之前匯出的持有項目 CSV：僅含既有 6 欄，無「用途」欄。"""
    df = pd.DataFrame(
        [
            (
                1,
                "範例定存",
                HOLDING_KIND.ASSET,
                ASSET_CATEGORIES.TIME_DEPOSIT,
                200000.0,
                200000.0,
            ),
            (
                2,
                "範例股票",
                HOLDING_KIND.ASSET,
                ASSET_CATEGORIES.TW_STOCK,
                100000.0,
                80000.0,
            ),
        ],
        columns=[
            "holding_id",
            "name",
            "kind",
            "category",
            "initial_market_value",
            "initial_cost",
        ],
    )
    return df.to_csv(index=False).encode("utf-8")


class TestHoldingsCsvPurposeRoundtrip:
    """SC-060：持有項目 CSV 匯出含用途欄，匯出入往返後用途保留。"""

    def _holdings_with_purpose(self) -> list[HoldingModel]:
        """兩筆項目（虛構值）：一筆用途購屋、一筆用途一般。"""
        return [
            HoldingModel(
                holding_id=1,
                name="範例定存",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TIME_DEPOSIT,
                initial_market_value=200000.0,
                initial_cost=200000.0,
                purpose=HOLDING_PURPOSE.HOUSE,
            ),
            HoldingModel(
                holding_id=2,
                name="範例股票",
                kind=HOLDING_KIND.ASSET,
                category=ASSET_CATEGORIES.TW_STOCK,
                initial_market_value=100000.0,
                initial_cost=80000.0,
                purpose=HOLDING_PURPOSE.GENERAL,
            ),
        ]

    @pytest.mark.scenario("SC-060")
    def test_sc060_export_holdings_csv_appends_purpose_column_at_end(self, service):
        # 用途欄附加於既有欄位之後，既有欄序不變
        csv_bytes = service.export_holdings_csv(holdings=self._holdings_with_purpose())
        df = _read_csv_bytes(csv_bytes)
        assert list(df.columns) == [
            "holding_id",
            "name",
            "kind",
            "category",
            "initial_market_value",
            "initial_cost",
            "purpose",
        ]
        assert list(df["purpose"]) == [HOLDING_PURPOSE.HOUSE, HOLDING_PURPOSE.GENERAL]

    @pytest.mark.scenario("SC-060")
    def test_sc060_roundtrip_preserves_purpose_after_export_then_reimport(self, service):
        # 匯出→清空→重新匯入，用途不遺失（純附加欄位須於備份鏈路中保存）
        holdings_csv = service.export_holdings_csv(holdings=self._holdings_with_purpose())

        holdings, _, _ = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=_empty_records_csv(service),
            targets_csv=service.export_targets_csv(targets=[]),
            target_db_empty=True,
        )
        assert holdings == self._holdings_with_purpose()


class TestLegacyHoldingsCsvWithoutPurposeColumn:
    """SC-061：舊版 CSV（無用途欄）仍可匯入，用途補為一般。"""

    @pytest.mark.scenario("SC-061")
    def test_sc061_legacy_csv_without_purpose_column_imports_and_defaults_to_general(
        self, service
    ):
        # 缺「用途」欄不觸發表頭驗證失敗（強制欄位維持既有 6 欄），匯入成功並補一般
        holdings, _, _ = service.parse_and_validate(
            holdings_csv=_legacy_holdings_csv_bytes(),
            records_csv=_empty_records_csv(service),
            targets_csv=service.export_targets_csv(targets=[]),
            target_db_empty=True,
        )
        assert len(holdings) == 2
        assert all(holding.purpose == HOLDING_PURPOSE.GENERAL for holding in holdings)

    @pytest.mark.scenario("SC-061")
    def test_sc061_blank_purpose_value_in_new_format_csv_defaults_to_general(self, service):
        # 用途欄存在但個別列留白：比照缺欄語意補一般（缺值等同缺欄，皆視為未填）
        csv_bytes = (
            b"holding_id,name,kind,category,initial_market_value,initial_cost,purpose\n"
            b"1,X,asset,,100.0,100.0,\n"
        )
        holdings, _, _ = service.parse_and_validate(
            holdings_csv=csv_bytes,
            records_csv=_empty_records_csv(service),
            targets_csv=service.export_targets_csv(targets=[]),
            target_db_empty=True,
        )
        assert holdings[0].purpose == HOLDING_PURPOSE.GENERAL


class TestHoldingsCsvInvalidPurposeValue:
    """SC-073：用途欄值非法（非一般/購屋）時拒絕整批匯入，比照既有性質/分類驗證慣例。"""

    @pytest.mark.scenario("SC-073")
    def test_sc073_invalid_purpose_value_is_rejected(self, service):
        # 用途欄出現既非一般也非購屋的值 → 拒絕整批匯入並點名非法值
        csv_bytes = (
            b"holding_id,name,kind,category,initial_market_value,initial_cost,purpose\n"
            b"1,X,asset,,100.0,100.0,vacation\n"
        )
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=csv_bytes,
                records_csv=_empty_records_csv(service),
                targets_csv=service.export_targets_csv(targets=[]),
                target_db_empty=True,
            )
        assert "vacation" in str(exc.value)


class TestImportDanglingRecordReference:
    """SC-038：月度紀錄指向不存在的持有項目時拒絕整批並點名該筆。"""

    @pytest.mark.scenario("SC-038")
    def test_sc038_record_referencing_unknown_holding_is_rejected(self, service):
        # 紀錄掛在主檔不存在的項目（holding_id=999）上 → 拒絕整批並點名該筆
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        targets_csv = service.export_targets_csv(targets=_targets())
        orphan = (
            b"holding_id,year_month,market_value,net_investment\n"
            b"999,2026-01,100.0,0.0\n"
        )
        with pytest.raises(DataValidationError) as exc:
            service.parse_and_validate(
                holdings_csv=holdings_csv,
                records_csv=orphan,
                targets_csv=targets_csv,
                target_db_empty=True,
            )
        assert "999" in str(exc.value)


def _legacy_records_csv_bytes() -> bytes:
    """模擬本 Change 之前匯出的月度紀錄 CSV：僅含既有 4 欄，無總成本與已實現收益欄。"""
    return (
        b"holding_id,year_month,market_value,net_investment\n"
        b"1,2026-01,510000.0,0.0\n"
        b"2,2026-01,800000.0,0.0\n"
    )


class TestLegacyRecordsCsvWithoutCostBasisColumns:
    """SC-084：舊格式 CSV（無總成本/已實現收益欄）仍可匯入，新欄位視為未填。"""

    @pytest.mark.scenario("SC-084")
    def test_sc084_legacy_csv_without_cost_basis_columns_imports_successfully(self, service):
        # 缺總成本/已實現收益欄不觸發表頭驗證失敗（強制欄位維持既有 4 欄），匯入成功
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        targets_csv = service.export_targets_csv(targets=_targets())
        holdings, records, targets = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=_legacy_records_csv_bytes(),
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        assert len(records) == 2
        # 市值與淨投入依原值還原
        assert records[0].market_value == 510000.0
        assert records[0].net_investment == 0.0

    @pytest.mark.scenario("SC-084")
    def test_sc084_legacy_csv_cost_basis_columns_default_to_none(self, service):
        # 還原後每筆紀錄的總成本與已實現收益皆視為未填
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        targets_csv = service.export_targets_csv(targets=_targets())
        _, records, _ = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=_legacy_records_csv_bytes(),
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        assert all(record.total_cost is None for record in records)
        assert all(record.realized_income is None for record in records)

    @pytest.mark.scenario("SC-084")
    def test_sc084_new_format_csv_blank_cost_basis_values_default_to_none(self, service):
        # 新格式欄位存在但個別列留白：比照缺欄語意還原為 None（缺值等同缺欄）
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        targets_csv = service.export_targets_csv(targets=_targets())
        csv_bytes = (
            b"holding_id,year_month,market_value,net_investment,total_cost,realized_income\n"
            b"1,2026-01,510000.0,0.0,,\n"
        )
        _, records, _ = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=csv_bytes,
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        assert records[0].total_cost is None
        assert records[0].realized_income is None


def _six_column_records_csv_bytes() -> bytes:
    """模擬前一個 Change 匯出的月度紀錄 CSV：6 欄（有總成本/已實現收益，無現金股利）。

    Returns:
        CSV 的位元組內容。
    """
    return (
        b"holding_id,year_month,market_value,net_investment,total_cost,realized_income\n"
        b"1,2026-01,510000.0,0.0,300000.0,8000.0\n"
        b"2,2026-01,800000.0,0.0,,\n"
    )


class TestLegacyRecordsCsvWithoutCashDividendColumn:
    """SC-084：舊格式 CSV（4 欄或前一 Change 的 6 欄）無現金股利欄，視為未填。"""

    @pytest.mark.scenario("SC-084")
    def test_sc084_four_column_csv_cash_dividend_is_none(self, service):
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        targets_csv = service.export_targets_csv(targets=_targets())
        _, records, _ = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=_legacy_records_csv_bytes(),
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        assert all(record.cash_dividend is None for record in records)

    @pytest.mark.scenario("SC-084")
    def test_sc084_six_column_csv_imports_with_cash_dividend_none(self, service):
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        targets_csv = service.export_targets_csv(targets=_targets())
        _, records, _ = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=_six_column_records_csv_bytes(),
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        assert len(records) == 2
        assert records[0].market_value == 510000.0
        assert records[0].net_investment == 0.0
        assert records[0].total_cost == 300000.0
        # 已實現收益原值全數保留，不拆出股利
        assert records[0].realized_income == 8000.0
        assert all(record.cash_dividend is None for record in records)

    @pytest.mark.scenario("SC-084")
    def test_sc084_new_format_blank_cash_dividend_defaults_to_none(self, service):
        holdings_csv = service.export_holdings_csv(holdings=_holdings())
        targets_csv = service.export_targets_csv(targets=_targets())
        csv_bytes = (
            b"holding_id,year_month,market_value,net_investment,total_cost,"
            b"realized_income,cash_dividend\n"
            b"1,2026-01,510000.0,0.0,300000.0,5000.0,\n"
        )
        _, records, _ = service.parse_and_validate(
            holdings_csv=holdings_csv,
            records_csv=csv_bytes,
            targets_csv=targets_csv,
            target_db_empty=True,
        )
        assert records[0].realized_income == 5000.0
        assert records[0].cash_dividend is None


class _FailingCursor:
    """包真實 cursor：第 fail_at 次 execute 起拋錯，模擬匯入寫入中途失敗。"""

    def __init__(self, real_cursor, *, fail_at: int) -> None:
        self._real_cursor = real_cursor
        self._fail_at = fail_at
        self._calls = 0

    def execute(self, *args: object, **kwargs: object):
        self._calls += 1
        if self._calls == self._fail_at:
            raise RuntimeError("模擬匯入寫入中途失敗")
        return self._real_cursor.execute(*args, **kwargs)


class _FlakyConnection:
    """包真實連線：cursor 注入中途失敗；可選擇 commit 失敗或 rollback 失敗。"""

    def __init__(
        self, real_conn, *, fail_at: int = 0, commit_fails: bool = False,
        rollback_fails: bool = False,
    ) -> None:
        self._real_conn = real_conn
        self._fail_at = fail_at
        self._commit_fails = commit_fails
        self._rollback_fails = rollback_fails

    def cursor(self):
        return _FailingCursor(self._real_conn.cursor(), fail_at=self._fail_at)

    def commit(self):
        if self._commit_fails:
            raise RuntimeError("模擬 commit 失敗")
        self._real_conn.commit()

    def rollback(self):
        if self._rollback_fails:
            raise RuntimeError("模擬 rollback 失敗")
        self._real_conn.rollback()


@pytest.fixture
def real_conn():
    connection = libsql.connect(":memory:")
    SchemaRepository(conn=connection).ensure_schema()
    return connection


def _parsed_import(service: DataIoService):
    """產出一份驗證通過的匯入內容（2 筆主檔、3 筆紀錄、2 筆目標）。"""
    holdings_csv = service.export_holdings_csv(holdings=_holdings())
    records_csv = service.export_records_csv(records=_records_df())
    targets_csv = service.export_targets_csv(targets=_targets())
    return service.parse_and_validate(
        holdings_csv=holdings_csv,
        records_csv=records_csv,
        targets_csv=targets_csv,
        target_db_empty=True,
    )


def _run_import(conn, tx_conn, parsed) -> None:
    """以真實的匯入寫入函式，用 tx_conn 開交易、conn 供各 Repository 持有。"""
    holdings, records, targets = parsed
    write_import(
        transaction_repo=TransactionRepository(conn=tx_conn),
        holding_repo=HoldingRepository(conn=conn),
        record_repo=RecordRepository(conn=conn),
        target_repo=TargetRepository(conn=conn),
        holdings=holdings,
        records=records,
        targets=targets,
    )


def _db_counts(conn) -> tuple[int, int, int]:
    return (
        len(HoldingRepository(conn=conn).list_holdings()),
        len(RecordRepository(conn=conn).read_all()),
        len(TargetRepository(conn=conn).read_targets()),
    )


class TestImportAtomic:
    """CSV 整批匯入跨三張表單一交易 —— SC-107。"""

    @pytest.mark.scenario("SC-107")
    def test_sc107_success_writes_all_three_tables(self, service, real_conn):
        _run_import(real_conn, real_conn, _parsed_import(service))
        assert _db_counts(real_conn) == (2, 3, 2)

    @pytest.mark.scenario("SC-107")
    def test_sc107_mid_failure_leaves_all_three_tables_empty(self, service, real_conn):
        # execute 順序：1 刪主檔、2-3 寫主檔、4 刪紀錄、5-6 寫紀錄（第 6 次失敗）
        parsed = _parsed_import(service)
        tx_conn = _FlakyConnection(real_conn, fail_at=6)

        with pytest.raises(PersistenceError) as exc_info:
            _run_import(real_conn, tx_conn, parsed)

        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert _db_counts(real_conn) == (0, 0, 0)

    @pytest.mark.scenario("SC-107")
    def test_sc107_failure_in_targets_step_also_rolls_back_earlier_tables(
        self, service, real_conn
    ):
        # 第 9 次 execute（寫第二筆目標）失敗：主檔與紀錄也要復原
        parsed = _parsed_import(service)
        tx_conn = _FlakyConnection(real_conn, fail_at=9)

        with pytest.raises(PersistenceError):
            _run_import(real_conn, tx_conn, parsed)

        assert _db_counts(real_conn) == (0, 0, 0)

    @pytest.mark.scenario("SC-107")
    def test_sc107_can_reimport_same_csv_after_failure(self, service, real_conn):
        parsed = _parsed_import(service)
        with pytest.raises(PersistenceError):
            _run_import(real_conn, _FlakyConnection(real_conn, fail_at=6), parsed)

        _run_import(real_conn, real_conn, parsed)

        assert _db_counts(real_conn) == (2, 3, 2)

    @pytest.mark.scenario("SC-107")
    def test_sc107_commit_failure_rolls_back_and_raises_same_friendly_error(
        self, service, real_conn
    ):
        parsed = _parsed_import(service)

        with pytest.raises(PersistenceError) as exc_info:
            _run_import(real_conn, _FlakyConnection(real_conn, commit_fails=True), parsed)

        assert str(exc_info.value) == PersistenceError.DEFAULT_MESSAGE
        assert _db_counts(real_conn) == (0, 0, 0)

    @pytest.mark.scenario("SC-107")
    def test_sc107_rollback_failure_still_raises_same_friendly_error(self, service, real_conn):
        parsed = _parsed_import(service)
        tx_conn = _FlakyConnection(real_conn, fail_at=6, rollback_fails=True)

        with pytest.raises(PersistenceError) as exc_info:
            _run_import(real_conn, tx_conn, parsed)

        assert str(exc_info.value) == PersistenceError.DEFAULT_MESSAGE


class TestImportFailureMessage:
    """寫入失敗時頁面顯示友善紅字、不露出原始錯誤 —— SC-107。"""

    @pytest.mark.scenario("SC-107")
    def test_sc107_failure_shows_friendly_error_without_raw_detail(self, service, real_conn):
        container = SimpleNamespace(
            data_io_service=service,
            holding_repo=HoldingRepository(conn=real_conn),
            record_repo=RecordRepository(conn=real_conn),
            target_repo=TargetRepository(conn=real_conn),
            transaction_repo=TransactionRepository(
                conn=_FlakyConnection(real_conn, fail_at=6)
            ),
        )
        at = AppTest.from_file(APP_DIR / "views" / "data_io.py")
        at.session_state["container"] = container
        at.run()
        for key, content in (
            ("up_holdings", service.export_holdings_csv(holdings=_holdings())),
            ("up_records", service.export_records_csv(records=_records_df())),
            ("up_targets", service.export_targets_csv(targets=_targets())),
        ):
            uploader = next(u for u in at.get("file_uploader") if u.key == key)
            uploader.set_value([("data.csv", content, "text/csv")])
        at.button[0].click()
        at.run()

        errors = [e.value for e in at.error]
        assert errors == ["匯入失敗，資料未變更，請重試"]
        assert not at.exception
        assert "模擬匯入寫入中途失敗" not in str(errors)
        assert _db_counts(real_conn) == (0, 0, 0)
