"""city/payload 測試：選取驗證、版位規格、JSON 契約欄位、旗桿順序、常數對照。資料皆為虛構值。"""

# ==== 原生（標準庫） ====
import dataclasses
import json

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.city import payload as pl
from asset_lab.city.geometry import GEOMETRY
from asset_lab.city.layout import CityLayout, layout_city
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
)
from asset_lab.models.results import (
    BucketProgress,
    CityBuildingState,
    CityFrame,
    CityHolding,
    CitySite,
    CityTimeline,
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

# (id, 名稱, 性質, 類別, 7 月值, 9 月值)；9 月值 None 代表有列但留空，缺 key 代表沒有該列
_ITEMS = (
    (1, "活存甲", HOLDING_KIND.ASSET, ASSET_CATEGORIES.DEMAND_DEPOSIT, 300_000.0, 320_000.0),
    (2, "台股甲", HOLDING_KIND.ASSET, ASSET_CATEGORIES.TW_STOCK, 2_000_000.0, 2_500_000.0),
    (3, "保單甲", HOLDING_KIND.ASSET, ASSET_CATEGORIES.INSURANCE, 600_000.0, None),
    (4, "房貸示意", HOLDING_KIND.LIABILITY, None, 2_000_000.0, 1_950_000.0),
)


def _city_holding(row, *, with_current: bool = True) -> CityHolding:
    hid, name, kind, category, prev, cur = row
    values: dict[str, float | None] = {_PREV: prev}
    if with_current:
        values[_CUR] = cur
    filled = [v for v in values.values() if v is not None]
    return CityHolding(
        holding_id=hid,
        name=name,
        kind=kind,
        category=category,
        peak_value=max(filled),
        month_values=values,
    )


def _timeline(*, extra_absent: bool = False) -> CityTimeline:
    holdings = [_city_holding(r) for r in _ITEMS]
    if extra_absent:
        holdings.append(
            _city_holding(
                (5, "定存甲", HOLDING_KIND.ASSET, ASSET_CATEGORIES.TIME_DEPOSIT, 9, 9)
            ).model_copy(update={"month_values": {_PREV: 900_000.0}, "peak_value": 900_000.0})
        )
    assets = [h.peak_value for h in holdings if h.kind == HOLDING_KIND.ASSET]
    liabs = [h.peak_value for h in holdings if h.kind == HOLDING_KIND.LIABILITY]
    return CityTimeline(
        months=[_PREV, _CUR],
        latest_month=_CUR,
        holdings=holdings,
        max_asset_value=max(assets),
        max_liability_value=max(liabs),
    )


def _states(timeline: CityTimeline, *, drift_for: str | None = None) -> list[CityBuildingState]:
    out = []
    for h in timeline.holdings:
        if _CUR not in h.month_values:
            status, value = _ABSENT, None
        elif h.month_values[_CUR] is None:
            status, value = _UNFILLED, None
        else:
            status, value = _PRESENT, h.month_values[_CUR]
        prev = h.month_values.get(_PREV)
        out.append(
            CityBuildingState(
                holding_id=h.holding_id,
                status=status,
                value=value,
                previous_month=_PREV,
                previous_status=_PRESENT,
                delta=(value - prev) if value is not None and prev is not None else None,
                drift=(
                    DriftRow(
                        category=drift_for,
                        current_weight=70.0,
                        target_weight=50.0,
                        drift=20.0,
                        needs_rebalance=True,
                    )
                    if drift_for is not None and status == _PRESENT and h.category == drift_for
                    else None
                ),
            )
        )
    return out


def _site(*, met=frozenset(), pct: float | None = 60.0, target: float = 3_000_000.0) -> CitySite:
    # 條件刻意以非 HOUSE_TRIGGER.ALL 的順序給，驗證 payload 會自行依 ALL 排序
    conds = [
        TriggerCondition(
            key=k,
            kind="subjective" if k in HOUSE_TRIGGER.SUBJECTIVE else "objective",
            met=k in met,
        )
        for k in reversed(HOUSE_TRIGGER.ALL)
    ]
    return CitySite(
        progress=BucketProgress(
            bucket_value=1_800_000.0,
            target_amount=target,
            gap=0.0,
            progress_pct=pct,
            reached_target_year=False,
        ),
        checklist=TriggerChecklist(conditions=conds, met_count=len(met), all_met=len(met) == 5),
    )


def _frame(timeline: CityTimeline, *, status=None, site=None, drift_for=None) -> CityFrame:
    return CityFrame(
        year_month=_CUR,
        is_latest=True,
        weather=status
        or ProtocolStatus(level_code="L2", status="ok", drawdown=-0.22, data_month_count=9),
        site=site or _site(),
        buildings=_states(timeline, drift_for=drift_for),
        drift_rows=[],
        house_purpose_categories=[],
    )


def _build(timeline=None, *, selected=None, **frame_kw) -> dict:
    timeline = timeline or _timeline()
    specs = pl.build_specs(timeline=timeline)
    layout = layout_city(specs=specs, max_asset=timeline.max_asset_value)
    frame = _frame(timeline, **frame_kw)
    return pl.build_payload(layout=layout, timeline=timeline, frame=frame, selected=selected)


def _by_id(payload: dict, holding_id: int) -> dict:
    key = pl.building_id(holding_id=holding_id)
    return next(b for b in payload["buildings"] if b["id"] == key)


class TestSelection:
    @pytest.mark.scenario("SC-159")
    def test_sc159_hint_text_is_defined_for_empty_selection(self):
        assert CITY_TEXT.CARD_HINT == "點建築或工地，查看該項目的細節"

    @pytest.mark.scenario("SC-159")
    @pytest.mark.parametrize("raw", [None, "", 12, 1.5, ["site"], {"a": 1}, b"site"])
    def test_sc159_non_id_selection_resolves_to_none(self, raw):
        assert pl.resolve_selection(selected=raw, timeline=_timeline()) is None

    @pytest.mark.scenario("SC-159")
    def test_sc159_stale_selection_is_silently_cleared(self):
        timeline = _timeline()
        stale = pl.building_id(holding_id=999)
        assert pl.resolve_selection(selected=stale, timeline=timeline) is None

    @pytest.mark.scenario("SC-159")
    def test_sc159_existing_building_and_site_are_kept(self):
        timeline = _timeline()
        bid = pl.building_id(holding_id=2)
        assert pl.resolve_selection(selected=bid, timeline=timeline) == bid
        assert pl.resolve_selection(selected=pl.SITE_ID, timeline=timeline) == pl.SITE_ID

    @pytest.mark.scenario("SC-159")
    def test_sc159_payload_selected_is_passed_through_or_null(self):
        bid = pl.building_id(holding_id=2)
        assert _build(selected=bid)["selected"] == bid
        assert _build(selected=None)["selected"] is None

    @pytest.mark.scenario("SC-159")
    def test_sc159_building_id_format(self):
        assert pl.building_id(holding_id=12) == "holding-12"


class TestSpecs:
    @pytest.mark.scenario("SC-152")
    def test_sc152_specs_have_one_site_and_one_per_holding(self):
        timeline = _timeline()
        specs = pl.build_specs(timeline=timeline)
        assert len(specs) == len(timeline.holdings) + 1
        assert [s.kind for s in specs].count("site") == 1
        assert len({s.id for s in specs}) == len(specs)

    @pytest.mark.scenario("SC-138")
    def test_sc138_liability_spec_is_pit_with_liability_prefix_reference(self):
        specs = {s.id: s for s in pl.build_specs(timeline=_timeline())}
        debt = specs[pl.building_id(holding_id=4)]
        assert debt.zone == CITY_ZONE.DEBT
        assert debt.shape == CITY_SHAPE.PIT
        assert debt.kind == "liability"
        assert debt.peak == 2_000_000.0
        assert debt.sub_reference.startswith(CITY_TEXT.LIABILITY_PREFIX)

    @pytest.mark.scenario("SC-152")
    def test_sc152_stock_spec_zone_shape_and_peak_reference(self):
        specs = {s.id: s for s in pl.build_specs(timeline=_timeline())}
        stock = specs[pl.building_id(holding_id=2)]
        assert stock.zone == CITY_ZONE.STOCK
        assert stock.shape == CITY_SHAPE.TOWER
        assert stock.sub_reference == "250.0 萬"

    @pytest.mark.scenario("SC-152")
    def test_sc152_site_spec_uses_geometry_reference_amount(self):
        specs = {s.id: s for s in pl.build_specs(timeline=_timeline())}
        site = specs[pl.SITE_ID]
        assert site.zone == CITY_ZONE.SITE
        assert site.shape == ""
        assert site.name == CITY_TEXT.SITE_NAME
        assert str(f"{GEOMETRY.site_reference_amount / 10000:,.1f}") in site.sub_reference


class TestContract:
    @pytest.mark.scenario("SC-152")
    def test_sc152_payload_is_json_serializable_and_roundtrips(self):
        payload = _build(selected=pl.SITE_ID)
        assert json.loads(json.dumps(payload)) == payload

    @pytest.mark.scenario("SC-152")
    def test_sc152_top_level_keys_match_contract(self):
        payload = _build()
        assert set(payload) == {
            "month", "aria_label", "ground", "top_pad", "compact", "roads", "blocks",
            "max_asset", "max_liab", "weather", "buildings", "site", "selected",
        }  # fmt: skip
        assert payload["month"] == _CUR
        assert payload["aria_label"] == CITY_TEXT.ARIA_LABEL
        assert payload["max_asset"] == 2_500_000.0
        assert payload["max_liab"] == 2_000_000.0

    @pytest.mark.scenario("SC-152")
    def test_sc152_layout_fields_come_from_layout(self):
        timeline = _timeline()
        specs = pl.build_specs(timeline=timeline)
        layout = layout_city(specs=specs, max_asset=timeline.max_asset_value)
        payload = pl.build_payload(
            layout=layout, timeline=timeline, frame=_frame(timeline), selected=None
        )
        assert payload["ground"] == [layout.ground_i, layout.ground_j]
        assert payload["top_pad"] == layout.top_pad
        assert payload["compact"] is layout.compact
        assert payload["roads"] == [list(r) for r in layout.roads]
        assert payload["blocks"] == [list(b) for b in layout.blocks]
        lots = dict(layout.lots)
        assert _by_id(payload, 2)["lot"] == list(lots[pl.building_id(holding_id=2)])
        assert payload["site"]["lot"] == list(lots[pl.SITE_ID])

    @pytest.mark.scenario("SC-152")
    def test_sc152_building_entry_fields_complete(self):
        entry = _by_id(_build(), 2)
        assert set(entry) == {
            "id", "name", "zone", "kind", "shape", "lot", "plate", "value", "vacant",
            "plate_mode", "sub", "tip", "warn",
        }  # fmt: skip
        assert set(entry["plate"]) == {"w", "h", "lines"}
        assert entry["zone"] == CITY_ZONE.STOCK
        assert entry["kind"] == "asset"
        assert entry["shape"] == CITY_SHAPE.TOWER
        assert entry["name"] == "台股甲"

    @pytest.mark.scenario("SC-139")
    def test_sc139_present_building_is_drawn_with_plate_and_tip(self):
        entry = _by_id(_build(), 2)
        assert entry["vacant"] is False
        assert entry["plate_mode"] == "normal"
        assert entry["value"] == 2_500_000.0
        assert entry["sub"] == "250.0 萬"
        assert entry["tip"][0] == "台股甲"
        assert entry["warn"] is False

    @pytest.mark.scenario("SC-139")
    def test_sc139_liability_sub_has_prefix(self):
        entry = _by_id(_build(), 4)
        assert entry["kind"] == "liability"
        assert entry["sub"] == "應繳 195.0 萬"

    @pytest.mark.scenario("SC-140")
    def test_sc140_unfilled_building_is_vacant_hidden_without_tip(self):
        entry = _by_id(_build(), 3)
        assert entry["vacant"] is True
        assert entry["plate_mode"] == "hidden"
        assert entry["value"] == 0
        assert entry["sub"] == ""
        assert entry["tip"] == []
        assert entry["warn"] is False

    @pytest.mark.scenario("SC-139")
    def test_sc139_absent_building_is_vacant_faded_with_absent_tip(self):
        entry = _by_id(_build(_timeline(extra_absent=True)), 5)
        assert entry["vacant"] is True
        assert entry["plate_mode"] == "faded"
        assert entry["value"] == 0
        assert entry["sub"] == ""
        assert entry["tip"] == ["定存甲", CITY_TEXT.ABSENT]
        assert entry["warn"] is False

    @pytest.mark.scenario("SC-150")
    def test_sc150_warn_only_on_present_building_of_flagged_category(self):
        payload = _build(drift_for=ASSET_CATEGORIES.TW_STOCK)
        assert _by_id(payload, 2)["warn"] is True
        assert _by_id(payload, 1)["warn"] is False
        assert _by_id(payload, 4)["warn"] is False

    @pytest.mark.scenario("SC-139")
    def test_sc139_buildings_follow_timeline_order(self):
        payload = _build()
        assert [b["id"] for b in payload["buildings"]] == [
            pl.building_id(holding_id=i) for i in (1, 2, 3, 4)
        ]

    @pytest.mark.scenario("SC-139")
    def test_sc139_vacant_lot_still_present_in_payload(self):
        # 空地要保留地塊，才畫得出空地與讓 absent 的淡化名稱牌可點
        entry = _by_id(_build(), 3)
        assert len(entry["lot"]) == 4
        assert entry["plate"]["lines"]

    @pytest.mark.scenario("SC-137")
    def test_sc137_zero_denominators_are_emitted_as_zero(self):
        timeline = _timeline().model_copy(
            update={"max_asset_value": 0.0, "max_liability_value": 0.0}
        )
        specs = pl.build_specs(timeline=timeline)
        layout = layout_city(specs=specs, max_asset=0.0)
        payload = pl.build_payload(
            layout=layout, timeline=timeline, frame=_frame(timeline), selected=None
        )
        assert payload["max_asset"] == 0
        assert payload["max_liab"] == 0


class TestSite:
    @pytest.mark.scenario("SC-146")
    def test_sc146_flags_follow_house_trigger_order_with_met_state(self):
        met = {HOUSE_TRIGGER.ANCHOR, HOUSE_TRIGGER.PAYMENT}
        flags = _build(site=_site(met=met))["site"]["flags"]
        assert [f["key"] for f in flags] == list(HOUSE_TRIGGER.ALL)
        assert len(flags) == 5
        assert {f["key"] for f in flags if f["met"]} == met

    @pytest.mark.scenario("SC-146")
    def test_sc146_incomplete_checklist_is_a_program_error(self):
        site = _site()
        broken = site.model_copy(
            update={
                "checklist": site.checklist.model_copy(
                    update={"conditions": site.checklist.conditions[:3]}
                )
            }
        )
        with pytest.raises(ValueError):
            _build(site=broken)

    @pytest.mark.scenario("SC-158")
    def test_sc158_site_entry_fields(self):
        site = _build()["site"]
        assert set(site) == {"id", "name", "lot", "plate", "progress", "sub", "tip", "flags"}
        assert site["id"] == pl.SITE_ID
        assert site["name"] == CITY_TEXT.SITE_NAME
        assert site["sub"] == "自備款 180.0 萬"
        assert site["tip"][0] == CITY_TEXT.SITE_NAME
        assert site["progress"] == pytest.approx(0.6)

    @pytest.mark.scenario("SC-158")
    @pytest.mark.parametrize(
        ("pct", "expected"), [(None, 0.0), (0.0, 0.0), (100.0, 1.0), (240.0, 1.0)]
    )
    def test_sc158_progress_is_capped_and_unset_target_is_zero(self, pct, expected):
        site = _build(site=_site(pct=pct, target=0.0 if pct is None else 3_000_000.0))["site"]
        assert site["progress"] == expected


class TestWeather:
    @pytest.mark.scenario("SC-147")
    def test_sc147_weather_comes_from_protocol_level(self):
        weather = _build()["weather"]
        assert set(weather) == {"sky", "severity", "title", "subtitle"}
        assert weather["sky"] == CITY_WEATHER.BY_LEVEL["L2"].sky
        assert "暴雨" in weather["title"]
        assert "22.0%" in weather["subtitle"]

    @pytest.mark.scenario("SC-148")
    def test_sc148_insufficient_data_uses_neutral_weather(self):
        status = ProtocolStatus(level_code="L0", status="insufficient_data", data_month_count=1)
        weather = _build(status=status)["weather"]
        assert weather["sky"] == CITY_WEATHER.NEUTRAL.sky
        assert weather["severity"] == CITY_WEATHER.NEUTRAL.severity


class TestValidation:
    def _parts(self):
        timeline = _timeline()
        specs = pl.build_specs(timeline=timeline)
        layout = layout_city(specs=specs, max_asset=timeline.max_asset_value)
        return timeline, layout

    @pytest.mark.scenario("SC-152")
    def test_sc152_overlapping_lots_raise_value_error(self):
        timeline, layout = self._parts()
        first = layout.lots[0][1]
        lots = (layout.lots[0], (layout.lots[1][0], first), *layout.lots[2:])
        bad = dataclasses.replace(layout, lots=lots)
        with pytest.raises(ValueError):
            pl.build_payload(layout=bad, timeline=timeline, frame=_frame(timeline), selected=None)

    @pytest.mark.scenario("SC-152")
    def test_sc152_lot_outside_ground_raises_value_error(self):
        timeline, layout = self._parts()
        key, (i, j, w, d) = layout.lots[0]
        bad = dataclasses.replace(
            layout, lots=((key, (layout.ground_i + 5, j, w, d)), *layout.lots[1:])
        )
        with pytest.raises(ValueError):
            pl.build_payload(layout=bad, timeline=timeline, frame=_frame(timeline), selected=None)

    @pytest.mark.scenario("SC-152")
    def test_sc152_missing_lot_for_building_raises_value_error(self):
        timeline, layout = self._parts()
        bad: CityLayout = dataclasses.replace(layout, lots=layout.lots[1:])
        with pytest.raises(ValueError):
            pl.build_payload(layout=bad, timeline=timeline, frame=_frame(timeline), selected=None)

    @pytest.mark.scenario("SC-139")
    def test_sc139_frame_not_aligned_with_timeline_raises_value_error(self):
        timeline, layout = self._parts()
        frame = _frame(timeline)
        bad = frame.model_copy(update={"buildings": frame.buildings[:-1]})
        with pytest.raises(ValueError):
            pl.build_payload(layout=layout, timeline=timeline, frame=bad, selected=None)


class TestConstantTables:
    @pytest.mark.scenario("SC-147")
    def test_sc147_weather_table_covers_every_protocol_level(self):
        assert set(CITY_WEATHER.BY_LEVEL) == set(PROTOCOL_LEVEL_CODE.ALL)

    @pytest.mark.scenario("SC-152")
    def test_sc152_zone_table_covers_every_asset_category(self):
        assert set(CITY_ZONE.BY_CATEGORY) == set(ASSET_CATEGORIES.ALL)

    @pytest.mark.scenario("SC-152")
    def test_sc152_shape_table_covers_every_building_zone(self):
        building_zones = {
            CITY_ZONE.CASH, CITY_ZONE.DEPOSIT, CITY_ZONE.STOCK, CITY_ZONE.INSURANCE, CITY_ZONE.DEBT,
        }  # fmt: skip
        assert set(CITY_SHAPE.BY_ZONE) == building_zones

    @pytest.mark.scenario("SC-146")
    def test_sc146_trigger_label_covers_every_trigger(self):
        assert set(HOUSE_TRIGGER.LABEL) == set(HOUSE_TRIGGER.ALL)
