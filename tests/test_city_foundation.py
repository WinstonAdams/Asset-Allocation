"""城市總覽基礎型別：常數對照表、例外、結果模型（純資料，無 SC，行為由後續 Task 驗證）。"""

# ==== 原生（標準庫） ====
import dataclasses

# ==== 第三方套件 ====
import pytest
from pydantic import ValidationError

# ==== 專案內部 ====
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    CITY_BUILDING_STATUS,
    CITY_SHAPE,
    CITY_WEATHER,
    CITY_ZONE,
    HOUSE_TRIGGER,
    PROTOCOL_LEVEL_CODE,
    CityWeatherSpec,
)
from asset_lab.core.exceptions import AssetLabError, CityLayoutError
from asset_lab.models.results import (
    CityBuildingState,
    CityHolding,
    CityTimeline,
)


class TestCityConstants:
    @pytest.mark.scenario("SC-152")
    def test_zone_covers_all_asset_categories(self):
        assert set(CITY_ZONE.BY_CATEGORY) == set(ASSET_CATEGORIES.ALL)

    @pytest.mark.scenario("SC-152")
    def test_tw_and_us_stock_share_stock_zone(self):
        assert CITY_ZONE.BY_CATEGORY[ASSET_CATEGORIES.TW_STOCK] == CITY_ZONE.STOCK
        assert CITY_ZONE.BY_CATEGORY[ASSET_CATEGORIES.US_STOCK] == CITY_ZONE.STOCK

    @pytest.mark.scenario("SC-152")
    def test_every_non_site_zone_has_label_and_shape(self):
        zones = {z for z in CITY_ZONE.BY_CATEGORY.values()} | {CITY_ZONE.LIABILITY}
        assert zones <= set(CITY_ZONE.ZONE_LABEL)
        assert zones <= set(CITY_SHAPE.BY_ZONE)

    @pytest.mark.scenario("SC-147")
    def test_weather_covers_all_protocol_levels(self):
        assert set(CITY_WEATHER.BY_LEVEL) == set(PROTOCOL_LEVEL_CODE.ALL)
        assert all(isinstance(s, CityWeatherSpec) for s in CITY_WEATHER.BY_LEVEL.values())

    @pytest.mark.scenario("SC-148")
    def test_neutral_weather_is_calm(self):
        assert CITY_WEATHER.NEUTRAL.sky == "calm"
        assert CITY_WEATHER.NEUTRAL.severity == "neutral"

    @pytest.mark.scenario("SC-147")
    def test_weather_spec_is_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            CITY_WEATHER.NEUTRAL.name = "x"  # type: ignore[misc]

    @pytest.mark.scenario("SC-146")
    def test_trigger_label_covers_all_triggers_with_original_text(self):
        assert set(HOUSE_TRIGGER.LABEL) == set(HOUSE_TRIGGER.ALL)
        assert HOUSE_TRIGGER.LABEL == {
            "anchor": "定錨",
            "income": "收入",
            "down_payment": "自備",
            "payment": "月付",
            "cognition": "認知",
        }

    @pytest.mark.scenario("SC-139")
    def test_building_status_vacant_is_unfilled_and_absent(self):
        assert CITY_BUILDING_STATUS.VACANT == {
            CITY_BUILDING_STATUS.UNFILLED,
            CITY_BUILDING_STATUS.ABSENT,
        }
        assert CITY_BUILDING_STATUS.PRESENT not in CITY_BUILDING_STATUS.VACANT


class TestCityLayoutError:
    @pytest.mark.scenario("SC-163")
    def test_is_domain_error_with_displayable_message(self):
        err = CityLayoutError("無法排出")
        assert isinstance(err, AssetLabError)
        assert str(err) == "無法排出"


class TestCityResultModels:
    @pytest.mark.scenario("SC-139")
    def test_holding_category_defaults_none_and_keeps_none_month_value(self):
        holding = CityHolding(
            holding_id=2, name="虛構貸款", kind="liability",
            peak_value=0.0, month_values={"2026-01": None},
        )
        assert holding.category is None
        assert holding.month_values["2026-01"] is None
        with pytest.raises(ValidationError):
            holding.peak_value = 99.0

    @pytest.mark.scenario("SC-151")
    def test_timeline_is_frozen_and_latest_defaults_none(self):
        timeline = CityTimeline(
            months=[], holdings=[], max_asset_value=0.0, max_liability_value=0.0
        )
        assert timeline.latest_month is None
        with pytest.raises(ValidationError):
            timeline.months = ["2026-01"]

    @pytest.mark.scenario("SC-139")
    def test_building_state_optional_fields_default_none(self):
        state = CityBuildingState(holding_id=1, status=CITY_BUILDING_STATUS.ABSENT)
        assert state.value is None
        assert state.previous_month is None
        assert state.previous_status is None
        assert state.delta is None
        assert state.drift is None
        with pytest.raises(ValidationError):
            state.value = 1.0
