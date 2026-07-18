# ==== 原生（標準庫） ====
import io

# ==== 第三方套件 ====
import pandas as pd
import pytest

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, HOLDING_KIND
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.target import TargetAllocationModel
from asset_lab.services.data_io_service import DataIoService


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
    """主檔對應的月度紀錄（資產市值/淨投入、負債餘額），欄序同 Repository.read_all。"""
    return pd.DataFrame(
        [
            (1, "2026-01", 510000.0, 0.0),
            (1, "2026-02", 0.0, -520000.0),
            (2, "2026-01", 800000.0, 0.0),
        ],
        columns=["holding_id", "year_month", "market_value", "net_investment"],
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
        # 匯出主檔 CSV：第一列為表頭，含全部項目（資產與負債）與其性質/初始市值/初始成本/分類
        csv_bytes = service.export_holdings_csv(holdings=_holdings())
        df = _read_csv_bytes(csv_bytes)
        assert list(df.columns) == [
            "holding_id",
            "name",
            "kind",
            "category",
            "initial_market_value",
            "initial_cost",
        ]
        assert list(df["holding_id"]) == [1, 2]
        assert list(df["name"]) == ["台積電", "房貸"]
        assert list(df["kind"]) == [HOLDING_KIND.ASSET, HOLDING_KIND.LIABILITY]

    @pytest.mark.scenario("SC-031")
    def test_sc031_export_records_has_header_and_all_rows(self, service):
        # 匯出月度紀錄 CSV：含表頭與全部月度列（資產市值/淨投入、負債餘額）
        csv_bytes = service.export_records_csv(records=_records_df())
        df = _read_csv_bytes(csv_bytes)
        assert list(df.columns) == [
            "holding_id",
            "year_month",
            "market_value",
            "net_investment",
        ]
        assert len(df) == 3

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
                holding_id=1, year_month="2026-01", market_value=510000.0, net_investment=0.0
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
