"""city/presentation 測試：分區外形、金額文字、天氣、小卡內容。資料一律為虛構值。"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.city import presentation as p
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    CITY_BUILDING_STATUS,
    CITY_SHAPE,
    CITY_TEXT,
    CITY_WEATHER,
    CITY_ZONE,
    HOLDING_KIND,
    HOUSE_TRIGGER,
    PROTOCOL_LEVEL_CODE,
    PROTOCOL_LEVELS,
)
from asset_lab.models.results import (
    BucketProgress,
    CityBuildingState,
    CityFrame,
    CityHolding,
    CitySite,
    DriftRow,
    ProtocolStatus,
    TriggerChecklist,
    TriggerCondition,
)

_PRESENT = CITY_BUILDING_STATUS.PRESENT
_UNFILLED = CITY_BUILDING_STATUS.UNFILLED
_ABSENT = CITY_BUILDING_STATUS.ABSENT
_PREV = "2026-07"
_CUR = "2026-09"


def _holding(*, kind=HOLDING_KIND.ASSET, category=ASSET_CATEGORIES.TW_STOCK) -> CityHolding:
    return CityHolding(
        holding_id=1,
        name="台股ETF甲",
        kind=kind,
        category=category if kind == HOLDING_KIND.ASSET else None,
        peak_value=1_300_000,
        month_values={_PREV: 1_000_000, _CUR: 1_300_000},
    )


def _state(
    *,
    status=_PRESENT,
    value: float | None = 1_300_000,
    previous_status: str | None = _PRESENT,
    delta: float | None = 300_000,
    drift: DriftRow | None = None,
) -> CityBuildingState:
    return CityBuildingState(
        holding_id=1,
        status=status,
        value=value,
        previous_month=_PREV if previous_status is not None else None,
        previous_status=previous_status,
        delta=delta,
        drift=drift,
    )


def _progress(*, bucket=1_800_000, target=3_000_000, pct: float | None = 60.0) -> BucketProgress:
    return BucketProgress(
        bucket_value=bucket,
        target_amount=target,
        gap=max(target - bucket, 0),
        progress_pct=pct,
        years_to_target=3,
        reached_target_year=False,
        required_annual_accumulation=400_000,
    )


def _checklist(met: set[str]) -> TriggerChecklist:
    conds = [
        TriggerCondition(
            key=k,
            kind="subjective" if k in HOUSE_TRIGGER.SUBJECTIVE else "objective",
            met=k in met,
        )
        for k in HOUSE_TRIGGER.ALL
    ]
    return TriggerChecklist(conditions=conds, met_count=len(met), all_met=len(met) == 5)


def _site(*, met=frozenset({HOUSE_TRIGGER.ANCHOR, HOUSE_TRIGGER.COGNITION}), **kw) -> CitySite:
    return CitySite(progress=_progress(**kw), checklist=_checklist(set(met)))


def _frame(*, is_latest=True, site=None, house_cats=()) -> CityFrame:
    return CityFrame(
        year_month=_CUR,
        is_latest=is_latest,
        weather=ProtocolStatus(level_code="L0", status="ok", data_month_count=5),
        site=site or _site(),
        buildings=[],
        drift_rows=[],
        house_purpose_categories=list(house_cats),
    )


def _flat(card: p.CityCard) -> str:
    return " ".join([card.title, *[f"{a} {b}" for a, b in card.rows], *card.notes])


class TestZoneShapeAmount:
    @pytest.mark.scenario("SC-157")
    def test_zone_for_asset_and_liability(self):
        assert (
            p.zone_for(kind=HOLDING_KIND.ASSET, category=ASSET_CATEGORIES.US_STOCK)
            == CITY_ZONE.STOCK
        )
        assert p.zone_for(kind=HOLDING_KIND.LIABILITY, category=None) == CITY_ZONE.DEBT

    @pytest.mark.scenario("SC-157")
    def test_shape_for_zone(self):
        assert p.shape_for(zone=CITY_ZONE.INSURANCE) == CITY_SHAPE.STATION
        assert p.shape_for(zone=CITY_ZONE.DEBT) == CITY_SHAPE.PIT

    @pytest.mark.scenario("SC-157")
    def test_amount_text_one_decimal_wan_with_thousands(self):
        assert p.amount_text(value=1_300_000) == "130.0 萬"
        assert p.amount_text(value=12_345_000) == "1,234.5 萬"
        assert p.amount_text(value=0) == "0.0 萬"

    @pytest.mark.scenario("SC-157")
    def test_plate_sub_liability_has_prefix(self):
        assert p.plate_sub(kind=HOLDING_KIND.ASSET, value=1_300_000) == "130.0 萬"
        assert p.plate_sub(kind=HOLDING_KIND.LIABILITY, value=500_000) == (
            f"{CITY_TEXT.LIABILITY_PREFIX} 50.0 萬"
        )

    @pytest.mark.scenario("SC-158")
    def test_site_sub_has_prefix(self):
        assert p.site_sub(bucket_value=1_800_000) == f"{CITY_TEXT.SITE_AMOUNT_PREFIX} 180.0 萬"


class TestWeather:
    @pytest.mark.scenario("SC-147")
    @pytest.mark.parametrize(
        ("code", "name"),
        [("L0", "晴"), ("L1", "多雲"), ("L2", "暴雨"), ("L3", "颱風")],
    )
    def test_sc147_weather_name_per_level(self, code, name):
        status = ProtocolStatus(level_code=code, status="ok", drawdown=-0.22, data_month_count=6)
        d = p.weather_display(status=status)
        label = next(s.label for s in PROTOCOL_LEVELS if s.code == code)
        assert d.sky == CITY_WEATHER.BY_LEVEL[code].sky
        assert d.severity == CITY_WEATHER.BY_LEVEL[code].severity
        assert name in d.title and code in d.title and label in d.title

    @pytest.mark.scenario("SC-147")
    def test_sc147_subtitle_shows_drawdown_percent(self):
        status = ProtocolStatus(
            level_code=PROTOCOL_LEVEL_CODE.L2, status="ok", drawdown=-0.22, data_month_count=6
        )
        d = p.weather_display(status=status)
        assert d.subtitle == CITY_TEXT.DRAWDOWN.format(pct="22.0%")

    @pytest.mark.scenario("SC-148")
    @pytest.mark.parametrize("flag", ["insufficient_data", "no_data"])
    def test_sc148_insufficient_data_is_neutral(self, flag):
        status = ProtocolStatus(level_code="L0", status=flag, data_month_count=2)
        d = p.weather_display(status=status)
        assert d.sky == CITY_WEATHER.NEUTRAL.sky == "calm"
        assert d.severity == "neutral"
        assert d.title == CITY_WEATHER.NEUTRAL.name
        assert "資料" in d.subtitle
        assert "回撤" not in d.subtitle


class TestBuildingCard:
    @pytest.mark.scenario("SC-157")
    def test_sc157_card_has_name_category_value(self):
        card = p.building_card(holding=_holding(), state=_state(), frame=_frame())
        assert card.title == "台股ETF甲"
        rows = dict(card.rows)
        assert rows[CITY_TEXT.CARD_LABEL_CATEGORY] == ASSET_CATEGORIES.TW_STOCK
        assert rows[CITY_TEXT.CARD_LABEL_VALUE] == "130.0 萬"

    @pytest.mark.scenario("SC-157")
    def test_sc157_liability_category_shows_debt_label(self):
        card = p.building_card(
            holding=_holding(kind=HOLDING_KIND.LIABILITY),
            state=_state(),
            frame=_frame(),
        )
        category = dict(card.rows)[CITY_TEXT.CARD_LABEL_CATEGORY]
        assert category == CITY_ZONE.ZONE_LABEL[CITY_ZONE.DEBT]

    @pytest.mark.scenario("SC-157")
    def test_sc157_absent_card_notes_no_such_item(self):
        card = p.building_card(
            holding=_holding(),
            state=_state(status=_ABSENT, value=None, previous_status=None, delta=None),
            frame=_frame(),
        )
        assert CITY_TEXT.ABSENT in card.notes
        assert CITY_TEXT.CARD_LABEL_VALUE not in dict(card.rows)

    @pytest.mark.scenario("SC-142")
    def test_sc142_compare_names_actual_previous_month_and_increase(self):
        card = p.building_card(holding=_holding(), state=_state(), frame=_frame())
        compare = dict(card.rows)[CITY_TEXT.CARD_LABEL_COMPARE]
        assert CITY_TEXT.COMPARE_WITH.format(month=_PREV) in compare
        assert "增加 30.0 萬" in compare
        assert "2026-08" not in compare

    @pytest.mark.scenario("SC-142")
    def test_sc142_decrease_and_flat(self):
        down = p.building_card(holding=_holding(), state=_state(delta=-50_000), frame=_frame())
        flat = p.building_card(holding=_holding(), state=_state(delta=0), frame=_frame())
        assert "減少 5.0 萬" in dict(down.rows)[CITY_TEXT.CARD_LABEL_COMPARE]
        assert CITY_TEXT.CARD_DELTA_FLAT in dict(flat.rows)[CITY_TEXT.CARD_LABEL_COMPARE]

    @pytest.mark.scenario("SC-142")
    def test_sc142_earliest_month_has_no_compare(self):
        card = p.building_card(
            holding=_holding(),
            state=_state(previous_status=None, delta=None),
            frame=_frame(),
        )
        assert CITY_TEXT.CARD_LABEL_COMPARE not in dict(card.rows)

    @pytest.mark.scenario("SC-142")
    def test_sc142_previous_absent_text(self):
        card = p.building_card(
            holding=_holding(),
            state=_state(previous_status=_ABSENT, delta=None),
            frame=_frame(),
        )
        assert dict(card.rows)[CITY_TEXT.CARD_LABEL_COMPARE] == CITY_TEXT.PREVIOUS_ABSENT.format(
            month=_PREV
        )

    @pytest.mark.scenario("SC-142")
    def test_sc142_previous_unfilled_text(self):
        card = p.building_card(
            holding=_holding(),
            state=_state(previous_status=_UNFILLED, delta=None),
            frame=_frame(),
        )
        assert dict(card.rows)[CITY_TEXT.CARD_LABEL_COMPARE] == CITY_TEXT.PREVIOUS_UNFILLED.format(
            month=_PREV
        )

    @pytest.mark.scenario("SC-142")
    def test_sc142_unfilled_hides_value_and_delta(self):
        card = p.building_card(
            holding=_holding(),
            state=_state(status=_UNFILLED, value=None, delta=None),
            frame=_frame(),
        )
        assert card.notes == (CITY_TEXT.UNFILLED,) or CITY_TEXT.UNFILLED in card.notes
        labels = dict(card.rows)
        assert CITY_TEXT.CARD_LABEL_VALUE not in labels
        assert CITY_TEXT.CARD_LABEL_COMPARE not in labels

    @pytest.mark.scenario("SC-157")
    def test_drift_row_and_notes_by_frame(self):
        drift = DriftRow(
            category=ASSET_CATEGORIES.TW_STOCK,
            current_weight=55.0,
            target_weight=40.0,
            drift=15.0,
            needs_rebalance=True,
        )
        hist = p.building_card(
            holding=_holding(),
            state=_state(drift=drift),
            frame=_frame(is_latest=False, house_cats=[ASSET_CATEGORIES.TW_STOCK]),
        )
        assert CITY_TEXT.CARD_LABEL_DRIFT in dict(hist.rows)
        assert CITY_TEXT.BY_CURRENT_SETTINGS in hist.notes
        assert CITY_TEXT.INCLUDES_HOUSE_PURPOSE in hist.notes
        latest = p.building_card(
            holding=_holding(), state=_state(drift=drift), frame=_frame(is_latest=True)
        )
        assert CITY_TEXT.BY_CURRENT_SETTINGS not in latest.notes
        assert CITY_TEXT.INCLUDES_HOUSE_PURPOSE not in latest.notes

    @pytest.mark.scenario("SC-157")
    def test_building_tip(self):
        tip = p.building_tip(holding=_holding(), state=_state())
        assert tip[0] == "台股ETF甲" and "130.0 萬" in tip[1]
        assert (
            p.building_tip(
                holding=_holding(), state=_state(status=_UNFILLED, value=None, delta=None)
            )
            == ()
        )
        absent = p.building_tip(
            holding=_holding(),
            state=_state(status=_ABSENT, value=None, previous_status=None, delta=None),
        )
        assert CITY_TEXT.ABSENT in absent


class TestSiteCard:
    @pytest.mark.scenario("SC-158")
    def test_sc158_amount_target_progress(self):
        card = p.site_card(site=_site(), is_latest=True)
        rows = dict(card.rows)
        assert card.title == CITY_TEXT.SITE_NAME
        assert rows[CITY_TEXT.CARD_LABEL_SITE_AMOUNT] == "180.0 萬"
        assert rows[CITY_TEXT.CARD_LABEL_SITE_TARGET] == "300.0 萬"
        assert rows[CITY_TEXT.CARD_LABEL_SITE_PROGRESS] == "60%"
        assert card.notes == ()

    @pytest.mark.scenario("SC-146")
    def test_sc146_five_conditions_in_fixed_order_with_status(self):
        card = p.site_card(site=_site(), is_latest=True)
        cond_rows = [r for r in card.rows if r[0] in HOUSE_TRIGGER.LABEL.values()]
        assert [r[0] for r in cond_rows] == [HOUSE_TRIGGER.LABEL[k] for k in HOUSE_TRIGGER.ALL]
        assert [r[1] for r in cond_rows] == [
            CITY_TEXT.MET,
            CITY_TEXT.NOT_MET,
            CITY_TEXT.NOT_MET,
            CITY_TEXT.NOT_MET,
            CITY_TEXT.MET,
        ]

    @pytest.mark.scenario("SC-146")
    def test_sc146_target_unset(self):
        card = p.site_card(site=_site(bucket=0, target=0, pct=None), is_latest=True)
        assert CITY_TEXT.TARGET_UNSET in _flat(card)
        assert CITY_TEXT.CARD_LABEL_SITE_PROGRESS not in dict(card.rows) or (
            dict(card.rows)[CITY_TEXT.CARD_LABEL_SITE_PROGRESS] == CITY_TEXT.TARGET_UNSET
        )

    @pytest.mark.scenario("SC-158")
    def test_sc158_percent_rounds_to_integer(self):
        card = p.site_card(site=_site(bucket=1_000_000, pct=33.33), is_latest=True)
        assert dict(card.rows)[CITY_TEXT.CARD_LABEL_SITE_PROGRESS] == "33%"

    @pytest.mark.scenario("SC-143")
    def test_sc143_history_card_annotated_and_hides_future_metrics(self):
        hist = p.site_card(site=_site(bucket=1_000_000, pct=33.3), is_latest=False)
        assert CITY_TEXT.BY_CURRENT_SETTINGS in hist.notes
        text = _flat(hist)
        assert "年" not in text.replace("依目前設定判定", "")
        assert "累積" not in text
        latest = p.site_card(site=_site(), is_latest=True)
        assert CITY_TEXT.BY_CURRENT_SETTINGS not in latest.notes

    @pytest.mark.scenario("SC-158")
    def test_site_tip(self):
        tip = p.site_tip(site=_site())
        assert tip[0] == CITY_TEXT.SITE_NAME
        assert f"{CITY_TEXT.SITE_AMOUNT_PREFIX} 180.0 萬" in tip
        assert CITY_TEXT.SITE_CONDITIONS.format(met=2, total=5) in tip
