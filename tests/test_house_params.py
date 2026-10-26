"""買房參數與主觀觸發勾選持久化：合併/驗證（純運算）+ 存取層 + 持久化（SC-054/055/068）。

effective_params／validate_params 為純運算，直接餵值驗證；持久化與「重啟後生效」則
透過 :memory: libsql 連線走 HouseParamRepository/SubjectiveTriggerRepository 與
bootstrap.build_container 的真實接線路徑驗證（比照既有 protocol_thresholds 測試慣例），
不連任何遠端 Turso。所有測試數值皆為虛構金額，不含任何個人化真實數字。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import libsql
import pytest

# ==== 專案內部 ====
from asset_lab import bootstrap
from asset_lab.core.constants import HOUSE_PARAM_DEFAULTS, HOUSE_PARAM_KEY, HOUSE_TRIGGER
from asset_lab.core.exceptions import DataValidationError, PersistenceError
from asset_lab.models.house import HouseParamModel, HouseParams, SubjectiveTriggerModel
from asset_lab.repositories.house_param_repository import HouseParamRepository
from asset_lab.repositories.query_metrics import QueryMetrics
from asset_lab.repositories.read_cache import ReadCache
from asset_lab.repositories.schema_repository import SchemaRepository
from asset_lab.repositories.subjective_trigger_repository import SubjectiveTriggerRepository
from asset_lab.services.house_service import HouseService
from tests.flaky_connection import FlakyConnection


@pytest.fixture
def conn():
    """每個 test 一個獨立記憶體 DB，建好表後交給 Repository（不連任何遠端 Turso）。"""
    connection = libsql.connect(":memory:")
    SchemaRepository(conn=connection).ensure_schema()
    yield connection


@pytest.fixture
def service() -> HouseService:
    return HouseService()


# 全數採中性/方法論預設的有效參數，供各測試以 model_copy 覆寫單一欄位使用。
_ALL_DEFAULTS = HouseParams(
    target_total_price=HOUSE_PARAM_DEFAULTS.TARGET_TOTAL_PRICE,
    target_year=HOUSE_PARAM_DEFAULTS.TARGET_YEAR,
    monthly_after_tax_income=HOUSE_PARAM_DEFAULTS.MONTHLY_AFTER_TAX_INCOME,
    income_threshold=HOUSE_PARAM_DEFAULTS.INCOME_THRESHOLD,
    cash_floor=HOUSE_PARAM_DEFAULTS.CASH_FLOOR,
    down_payment_ratio=HOUSE_PARAM_DEFAULTS.DOWN_PAYMENT_RATIO,
    payment_cap_ratio=HOUSE_PARAM_DEFAULTS.PAYMENT_CAP_RATIO,
    test_annual_rate=HOUSE_PARAM_DEFAULTS.TEST_ANNUAL_RATE,
    loan_years=HOUSE_PARAM_DEFAULTS.LOAN_YEARS,
)


class TestEffectiveParamsDefaults:
    """effective_params：未存/缺鍵時以中性預設補齊，不因缺值崩壞（SC-054 邊界）。"""

    @pytest.mark.scenario("SC-054")
    def test_sc054_never_configured_uses_all_neutral_defaults(self, service):
        # 資料庫完全沒有任何已存參數：個人化參數一律 0，政策比率採方法論預設
        params = service.effective_params(stored=[])
        assert params == _ALL_DEFAULTS

    @pytest.mark.scenario("SC-054")
    def test_sc054_single_stored_key_merges_with_remaining_defaults(self, service):
        # 只存了 9 個參數中的 1 個（目標總價），其餘 8 個仍補中性預設，不因缺其他鍵而失敗
        stored = [
            HouseParamModel(
                param_key=HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE, param_value=5_000_000.0
            )
        ]
        params = service.effective_params(stored=stored)
        assert params.target_total_price == 5_000_000.0
        assert params.target_year == HOUSE_PARAM_DEFAULTS.TARGET_YEAR
        assert params.down_payment_ratio == HOUSE_PARAM_DEFAULTS.DOWN_PAYMENT_RATIO

    @pytest.mark.scenario("SC-054")
    def test_sc054_partial_stored_mixes_stored_and_default_values(self, service):
        # 部分已存、部分未存：已存鍵用已存值，缺鍵補預設，兩者可混用
        stored = [
            HouseParamModel(
                param_key=HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE, param_value=5_000_000.0
            ),
            HouseParamModel(param_key=HOUSE_PARAM_KEY.DOWN_PAYMENT_RATIO, param_value=30.0),
        ]
        params = service.effective_params(stored=stored)
        assert params.target_total_price == 5_000_000.0
        assert params.down_payment_ratio == 30.0
        # 其餘鍵仍缺，各自補對應中性/方法論預設
        assert params.monthly_after_tax_income == HOUSE_PARAM_DEFAULTS.MONTHLY_AFTER_TAX_INCOME
        assert params.payment_cap_ratio == HOUSE_PARAM_DEFAULTS.PAYMENT_CAP_RATIO
        assert params.loan_years == HOUSE_PARAM_DEFAULTS.LOAN_YEARS

    @pytest.mark.scenario("SC-054")
    def test_sc054_target_year_and_loan_years_restored_as_int(self, service):
        # target_year/loan_years 於表中以 REAL 儲存，effective_params 邊界須還原為 int
        stored = [
            HouseParamModel(param_key=HOUSE_PARAM_KEY.TARGET_YEAR, param_value=2030.0),
            HouseParamModel(param_key=HOUSE_PARAM_KEY.LOAN_YEARS, param_value=20.0),
        ]
        params = service.effective_params(stored=stored)
        assert params.target_year == 2030
        assert isinstance(params.target_year, int)
        assert params.loan_years == 20
        assert isinstance(params.loan_years, int)


class TestHouseParamsPersistence:
    """買房參數存入後計算生效：已存值覆蓋、後續計算採新值（SC-054）。"""

    @pytest.mark.scenario("SC-054")
    def test_sc054_saved_target_total_price_and_ratio_compute_down_payment_target(
        self, conn, service
    ):
        # 使用者於設定頁填入目標總價 5,000,000 元、自備比率 30%（虛構值，符合隱私護欄）
        repo = HouseParamRepository(conn=conn)
        repo.upsert_param(
            param=HouseParamModel(
                param_key=HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE, param_value=5_000_000.0
            )
        )
        repo.upsert_param(
            param=HouseParamModel(
                param_key=HOUSE_PARAM_KEY.DOWN_PAYMENT_RATIO, param_value=30.0
            )
        )

        # 模擬回到買房頁或總覽頁：重新讀取後合併生效
        params = service.effective_params(stored=repo.read_params())

        assert params.target_total_price == 5_000_000.0
        assert params.down_payment_ratio == 30.0
        # 自備款目標 = 目標總價 × 自備比率
        bucket_target = params.target_total_price * params.down_payment_ratio / 100
        assert bucket_target == 1_500_000.0

    @pytest.mark.scenario("SC-054")
    def test_sc054_saved_params_persist_across_container_rebuild(self, conn):
        # 端到端：以 bootstrap 重新組裝容器（模擬 app 重啟）沿用同一底層連線，已存值仍在
        first_container = bootstrap.build_container(
            conn=conn,
            read_cache=ReadCache(ttl_seconds=300),
            query_metrics=QueryMetrics(),
        )
        first_container.house_param_repo.upsert_param(
            param=HouseParamModel(
                param_key=HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE, param_value=5_000_000.0
            )
        )

        restarted_container = bootstrap.build_container(
            conn=conn,
            read_cache=ReadCache(ttl_seconds=300),
            query_metrics=QueryMetrics(),
        )
        params = restarted_container.house_service.effective_params(
            stored=restarted_container.house_param_repo.read_params()
        )

        assert params.target_total_price == 5_000_000.0


class TestValidateParamsRejectsInvalid:
    """validate_params：逐項邊界驗證，非法值皆拋出（SC-055）。"""

    @pytest.mark.scenario("SC-055")
    @pytest.mark.parametrize("ratio", [0.0, 100.0, -5.0, 120.0])
    def test_sc055_invalid_down_payment_ratio_raises(self, service, ratio):
        params = _ALL_DEFAULTS.model_copy(update={"down_payment_ratio": ratio})
        with pytest.raises(DataValidationError):
            service.validate_params(params=params)

    @pytest.mark.scenario("SC-055")
    @pytest.mark.parametrize("ratio", [0.0, 100.0, -5.0, 120.0])
    def test_sc055_invalid_payment_cap_ratio_raises(self, service, ratio):
        params = _ALL_DEFAULTS.model_copy(update={"payment_cap_ratio": ratio})
        with pytest.raises(DataValidationError):
            service.validate_params(params=params)

    @pytest.mark.scenario("SC-055")
    def test_sc055_negative_test_annual_rate_raises(self, service):
        params = _ALL_DEFAULTS.model_copy(update={"test_annual_rate": -0.5})
        with pytest.raises(DataValidationError):
            service.validate_params(params=params)

    @pytest.mark.scenario("SC-055")
    @pytest.mark.parametrize("loan_years", [0, -1])
    def test_sc055_invalid_loan_years_raises(self, service, loan_years):
        params = _ALL_DEFAULTS.model_copy(update={"loan_years": loan_years})
        with pytest.raises(DataValidationError):
            service.validate_params(params=params)

    @pytest.mark.scenario("SC-055")
    @pytest.mark.parametrize(
        "field",
        ["target_total_price", "monthly_after_tax_income", "income_threshold", "cash_floor"],
    )
    def test_sc055_negative_amount_fields_raise(self, service, field):
        params = _ALL_DEFAULTS.model_copy(update={field: -1.0})
        with pytest.raises(DataValidationError):
            service.validate_params(params=params)

    @pytest.mark.scenario("SC-055")
    def test_sc055_negative_target_year_raises(self, service):
        params = _ALL_DEFAULTS.model_copy(update={"target_year": -1})
        with pytest.raises(DataValidationError):
            service.validate_params(params=params)

    @pytest.mark.scenario("SC-055")
    def test_sc055_zero_test_annual_rate_is_valid(self, service):
        # 驗算利率 0 為合法值（不同於比率型參數的 0 視為非法）
        params = _ALL_DEFAULTS.model_copy(update={"test_annual_rate": 0.0})
        service.validate_params(params=params)

    @pytest.mark.scenario("SC-055")
    def test_sc055_all_defaults_are_valid_including_zero_amount_and_year(self, service):
        # 中性/方法論預設整組皆合法：金額類與目標年份的 0（未設定）不被拒絕
        service.validate_params(params=_ALL_DEFAULTS)


class TestInvalidParamsDoNotPersist:
    """驗證失敗時既有參數維持不變、不落 DB（SC-055 端到端）。"""

    @pytest.mark.scenario("SC-055")
    def test_sc055_rejected_save_does_not_change_persisted_down_payment_ratio(
        self, conn, service
    ):
        repo = HouseParamRepository(conn=conn)
        repo.upsert_param(
            param=HouseParamModel(
                param_key=HOUSE_PARAM_KEY.DOWN_PAYMENT_RATIO, param_value=30.0
            )
        )

        # 模擬設定頁存前驗證：驗證失敗即拋出，呼叫端（view）不會再呼叫 upsert_param
        invalid_candidate = _ALL_DEFAULTS.model_copy(update={"down_payment_ratio": 0.0})
        with pytest.raises(DataValidationError):
            service.validate_params(params=invalid_candidate)

        persisted = service.effective_params(stored=repo.read_params())
        assert persisted.down_payment_ratio == 30.0


class TestSubjectiveTriggerPersistence:
    """主觀觸發條件（定錨、認知）勾選狀態持久化（SC-068）。"""

    @pytest.mark.scenario("SC-068")
    def test_sc068_no_stored_record_returns_empty_list(self, conn):
        # 從未操作過：資料庫無紀錄，read_triggers 回空清單（消費端視同未勾選）
        repo = SubjectiveTriggerRepository(conn=conn)
        assert repo.read_triggers() == []

    @pytest.mark.scenario("SC-068")
    def test_sc068_checking_anchor_persists_and_reload_shows_checked(self, conn):
        repo = SubjectiveTriggerRepository(conn=conn)
        repo.upsert_trigger(
            trigger=SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True)
        )

        reloaded = {t.trigger_key: t.checked for t in repo.read_triggers()}

        assert reloaded[HOUSE_TRIGGER.ANCHOR] is True

    @pytest.mark.scenario("SC-068")
    def test_sc068_anchor_and_cognition_are_independent(self, conn):
        # 只勾選定錨：認知不受影響，仍無紀錄（視同未勾選）
        repo = SubjectiveTriggerRepository(conn=conn)
        repo.upsert_trigger(
            trigger=SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True)
        )

        reloaded = {t.trigger_key: t.checked for t in repo.read_triggers()}

        assert reloaded[HOUSE_TRIGGER.ANCHOR] is True
        assert HOUSE_TRIGGER.COGNITION not in reloaded

    @pytest.mark.scenario("SC-068")
    def test_sc068_unchecking_after_checked_persists_as_unchecked(self, conn):
        # 勾選後再取消：重新讀取（模擬重啟）後為未勾選
        repo = SubjectiveTriggerRepository(conn=conn)
        repo.upsert_trigger(
            trigger=SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=True)
        )
        repo.upsert_trigger(
            trigger=SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.COGNITION, checked=False)
        )

        reloaded = {t.trigger_key: t.checked for t in repo.read_triggers()}

        assert reloaded[HOUSE_TRIGGER.COGNITION] is False

    @pytest.mark.scenario("SC-068")
    def test_sc068_checked_state_persists_across_container_rebuild(self, conn):
        # 端到端：模擬「關閉並重新開啟應用程式」——以 bootstrap 重新組裝容器沿用同一連線
        first_container = bootstrap.build_container(
            conn=conn,
            read_cache=ReadCache(ttl_seconds=300),
            query_metrics=QueryMetrics(),
        )
        first_container.subjective_trigger_repo.upsert_trigger(
            trigger=SubjectiveTriggerModel(trigger_key=HOUSE_TRIGGER.ANCHOR, checked=True)
        )

        restarted_container = bootstrap.build_container(
            conn=conn,
            read_cache=ReadCache(ttl_seconds=300),
            query_metrics=QueryMetrics(),
        )
        reloaded = {
            t.trigger_key: t.checked
            for t in restarted_container.subjective_trigger_repo.read_triggers()
        }

        assert reloaded[HOUSE_TRIGGER.ANCHOR] is True
        assert HOUSE_TRIGGER.COGNITION not in reloaded


def _stored_params(conn) -> dict[str, float]:
    return {p.param_key: p.param_value for p in HouseParamRepository(conn=conn).read_params()}


class TestBatchUpsertParams:
    """買房參數九筆整批寫入同一交易（SC-128／SC-129）。"""

    @pytest.mark.scenario("SC-128")
    def test_sc128_build_models_returns_nine_params(self, service):
        models = service.build_param_models(params=_ALL_DEFAULTS)

        assert len(models) == 9
        assert len({m.param_key for m in models}) == 9

    @pytest.mark.scenario("SC-128")
    def test_sc128_build_models_rejects_invalid_params(self, service):
        with pytest.raises(DataValidationError):
            service.build_param_models(params=_ALL_DEFAULTS.model_copy(update={"loan_years": 0}))

    @pytest.mark.scenario("SC-128")
    def test_sc128_batch_upsert_writes_all_nine_together(self, conn, service):
        HouseParamRepository(conn=conn).upsert_params(
            params=service.build_param_models(params=_ALL_DEFAULTS)
        )

        assert len(_stored_params(conn)) == 9

    @pytest.mark.scenario("SC-128")
    def test_sc128_batch_upsert_empty_list_issues_no_write(self, conn):
        flaky = FlakyConnection(conn, fail_at=1)

        HouseParamRepository(conn=flaky).upsert_params(params=[])

        assert _stored_params(conn) == {}

    @pytest.mark.scenario("SC-129")
    def test_sc129_failure_at_nth_row_keeps_all_original_values(self, conn, service):
        HouseParamRepository(conn=conn).upsert_params(
            params=service.build_param_models(params=_ALL_DEFAULTS)
        )
        before = _stored_params(conn)
        changed = _ALL_DEFAULTS.model_copy(update={"loan_years": 20, "target_year": 2040})
        flaky = FlakyConnection(conn, fail_at=5)

        with pytest.raises(PersistenceError) as exc_info:
            HouseParamRepository(conn=flaky).upsert_params(
                params=service.build_param_models(params=changed)
            )

        assert str(exc_info.value) == "存檔失敗，資料未變更，請重試"
        assert _stored_params(conn) == before
