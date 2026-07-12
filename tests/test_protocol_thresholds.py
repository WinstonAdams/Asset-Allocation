"""回撤門檻設定端到端：驗證/預設補齊 + 持久化 + 存前拒絕（SC-046/047）。

effective_thresholds／validate_thresholds 為純運算，直接餵值驗證；持久化與「重啟後
生效」則透過 :memory: libsql 連線走 ProtocolThresholdRepository 與 bootstrap.build_container
的真實接線路徑驗證（比照既有 target_allocations 的測試慣例），不連任何遠端 Turso。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import libsql
import pytest

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.constants import PROTOCOL_LEVEL_CODE, PROTOCOL_MIN_DATA_MONTHS
from asset_lab.core.exceptions import DataValidationError
from asset_lab.models.protocol import ProtocolThresholdModel, ProtocolThresholds
from asset_lab.models.results import CumulativeTwrPoint
from asset_lab.repositories.protocol_threshold_repository import ProtocolThresholdRepository
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.services.protocol_service import ProtocolService


@pytest.fixture
def conn():
    """每個 test 一個獨立記憶體 DB，建好表後交給 Repository（不連任何遠端 Turso）。"""
    connection = libsql.connect(":memory:")
    SchemaRepository(conn=connection).ensure_schema()
    yield connection


@pytest.fixture
def service() -> ProtocolService:
    return ProtocolService()


def _series(cumulative_twrs: list[float]) -> list[CumulativeTwrPoint]:
    """以累積 TWR 清單組成逐月序列（年月依序遞增，僅測試用）。"""
    return [
        CumulativeTwrPoint(year_month=f"2026-{index + 1:02d}", cumulative_twr=twr)
        for index, twr in enumerate(cumulative_twrs)
    ]


class TestEffectiveThresholdsDefaults:
    """effective_thresholds：未設定/缺級時以預設補齊，不因缺值崩壞（SC-046 邊界）。"""

    @pytest.mark.scenario("SC-046")
    def test_sc046_never_configured_uses_all_defaults(self, service):
        # 使用者從未設定過任何門檻：全數採預設 L1=10/L2=20/L3=30
        thresholds = service.effective_thresholds(stored=[])
        assert thresholds == ProtocolThresholds(l1=10.0, l2=20.0, l3=30.0)

    @pytest.mark.scenario("SC-046")
    def test_sc046_missing_level_falls_back_to_default(self, service):
        # 只保存了 L1，L2/L3 缺值：缺的等級以預設補齊，不因缺值崩壞
        stored = [
            ProtocolThresholdModel(level=PROTOCOL_LEVEL_CODE.L1, drawdown_threshold=12.0)
        ]
        thresholds = service.effective_thresholds(stored=stored)
        assert thresholds == ProtocolThresholds(l1=12.0, l2=20.0, l3=30.0)

    @pytest.mark.scenario("SC-046")
    def test_sc046_all_levels_stored_overrides_all_defaults(self, service):
        # 三級皆已保存：全部改用保存值，不受預設影響
        stored = [
            ProtocolThresholdModel(level=PROTOCOL_LEVEL_CODE.L1, drawdown_threshold=12.0),
            ProtocolThresholdModel(level=PROTOCOL_LEVEL_CODE.L2, drawdown_threshold=25.0),
            ProtocolThresholdModel(level=PROTOCOL_LEVEL_CODE.L3, drawdown_threshold=35.0),
        ]
        thresholds = service.effective_thresholds(stored=stored)
        assert thresholds == ProtocolThresholds(l1=12.0, l2=25.0, l3=35.0)


class TestThresholdPersistence:
    """門檻可持久化，經 Repository/容器重建（模擬重啟）後仍生效（SC-046）。"""

    @pytest.mark.scenario("SC-046")
    def test_sc046_saved_thresholds_persist_across_repository_reload(self, conn):
        # 存三級門檻後，另建一個新 Repository 實例讀同一連線（模擬重啟後重新組裝 Repo）
        ProtocolThresholdRepository(conn=conn).upsert_threshold(
            threshold=ProtocolThresholdModel(
                level=PROTOCOL_LEVEL_CODE.L1, drawdown_threshold=12.0
            )
        )
        ProtocolThresholdRepository(conn=conn).upsert_threshold(
            threshold=ProtocolThresholdModel(
                level=PROTOCOL_LEVEL_CODE.L2, drawdown_threshold=25.0
            )
        )
        ProtocolThresholdRepository(conn=conn).upsert_threshold(
            threshold=ProtocolThresholdModel(
                level=PROTOCOL_LEVEL_CODE.L3, drawdown_threshold=35.0
            )
        )

        reloaded = {
            t.level: t.drawdown_threshold
            for t in ProtocolThresholdRepository(conn=conn).read_thresholds()
        }

        assert reloaded == {"L1": 12.0, "L2": 25.0, "L3": 35.0}

    @pytest.mark.scenario("SC-046")
    def test_sc046_thresholds_persist_across_container_rebuild(self, conn):
        # 端到端：以 bootstrap 重新組裝容器（模擬 app 重啟重建容器）沿用同一底層連線，
        # 門檻仍在——「重啟後生效」的持久化保證不因容器重建而丟失
        first_container = bootstrap.build_container(conn=conn)
        for level, value in (("L1", 12.0), ("L2", 25.0), ("L3", 35.0)):
            first_container.protocol_threshold_repo.upsert_threshold(
                threshold=ProtocolThresholdModel(level=level, drawdown_threshold=value)
            )

        restarted_container = bootstrap.build_container(conn=conn)
        thresholds = restarted_container.protocol_service.effective_thresholds(
            stored=restarted_container.protocol_threshold_repo.read_thresholds()
        )

        assert thresholds == ProtocolThresholds(l1=12.0, l2=25.0, l3=35.0)

    @pytest.mark.scenario("SC-046")
    def test_sc046_new_thresholds_change_level_assessment(self, service):
        # 存新門檻（L1=12/L2=25/L3=35）後，等級判定改用新門檻：
        # 目前回撤剛好 26%（>=L2 但 <L3）→ 判為 L2
        thresholds = ProtocolThresholds(l1=12.0, l2=25.0, l3=35.0)
        series = _series([-0.01, -0.02, -0.26])
        status = service.assess(
            series=series, thresholds=thresholds, min_data_months=PROTOCOL_MIN_DATA_MONTHS
        )
        assert status.level_code == PROTOCOL_LEVEL_CODE.L2


class TestValidateThresholdsRejectsInvalid:
    """validate_thresholds：非 0 < L1 < L2 < L3 一律拒絕（SC-047）。"""

    @pytest.mark.scenario("SC-047")
    @pytest.mark.parametrize(
        ("l1", "l2", "l3"),
        [
            (20.0, 10.0, 30.0),  # L1 > L2，順序顛倒
            (10.0, 10.0, 30.0),  # L1 = L2，非嚴格遞增
            (10.0, 20.0, 20.0),  # L2 = L3，非嚴格遞增（邊界擴充）
            (0.0, 20.0, 30.0),  # L1 為 0，須為正值
            (-5.0, 20.0, 30.0),  # L1 為負值
        ],
    )
    def test_sc047_invalid_order_raises_validation_error(self, service, l1, l2, l3):
        with pytest.raises(DataValidationError):
            service.validate_thresholds(l1=l1, l2=l2, l3=l3)

    @pytest.mark.scenario("SC-047")
    def test_sc047_valid_strictly_increasing_thresholds_pass(self, service):
        # 合法設定（12% < 25% < 35%）→ 不拋例外，通過驗證
        service.validate_thresholds(l1=12.0, l2=25.0, l3=35.0)


class TestInvalidThresholdsDoNotPersist:
    """驗證失敗時既有門檻維持不變、不落 DB（SC-047 端到端）。"""

    @pytest.mark.scenario("SC-047")
    def test_sc047_rejected_save_does_not_change_persisted_thresholds(self, conn, service):
        repo = ProtocolThresholdRepository(conn=conn)
        repo.upsert_threshold(
            threshold=ProtocolThresholdModel(level=PROTOCOL_LEVEL_CODE.L1, drawdown_threshold=10.0)
        )
        repo.upsert_threshold(
            threshold=ProtocolThresholdModel(level=PROTOCOL_LEVEL_CODE.L2, drawdown_threshold=20.0)
        )
        repo.upsert_threshold(
            threshold=ProtocolThresholdModel(level=PROTOCOL_LEVEL_CODE.L3, drawdown_threshold=30.0)
        )

        # 模擬設定頁存前驗證：驗證失敗即拋出，呼叫端（view）不會再呼叫 upsert_threshold
        with pytest.raises(DataValidationError):
            service.validate_thresholds(l1=20.0, l2=10.0, l3=30.0)

        unchanged = {t.level: t.drawdown_threshold for t in repo.read_thresholds()}
        assert unchanged == {"L1": 10.0, "L2": 20.0, "L3": 30.0}
