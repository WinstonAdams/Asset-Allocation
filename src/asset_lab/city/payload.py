"""城市 payload 組裝（純模組，不碰 st.*）：選取驗證、版位規格、前端 JSON 契約。

`build_payload` 是前後端契約的唯一產生者：前端只畫圖，所有業務判斷與顯示文字都在這裡決定。
"""

# ==== 原生（標準庫） ====
from collections.abc import Sequence

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.city import presentation
from asset_lab.city.geometry import GEOMETRY, Lot
from asset_lab.city.layout import (
    SPEC_KIND_SITE,
    CityLayout,
    CitySpec,
    PlateSize,
)
from asset_lab.core.constants import (
    CITY_BUILDING_STATUS,
    CITY_TEXT,
    CITY_ZONE,
    HOUSE_TRIGGER,
)
from asset_lab.models.results import (
    CityBuildingState,
    CityFrame,
    CityHolding,
    CitySite,
    CityTimeline,
)

SITE_ID = "site"

_BUILDING_ID_PREFIX = "holding-"
_PERCENT_DIVISOR = 100.0

# 名稱牌三種畫法：一般、淡化（沒有此項目）、隱藏（市值留空）
PLATE_NORMAL = "normal"
PLATE_FADED = "faded"
PLATE_HIDDEN = "hidden"

_PLATE_MODE_BY_STATUS = {
    CITY_BUILDING_STATUS.PRESENT: PLATE_NORMAL,
    CITY_BUILDING_STATUS.ABSENT: PLATE_FADED,
    CITY_BUILDING_STATUS.UNFILLED: PLATE_HIDDEN,
}


def building_id(*, holding_id: int) -> str:
    """建築在版位與 payload 的識別字串。"""
    return f"{_BUILDING_ID_PREFIX}{holding_id}"


def resolve_selection(*, selected: object, timeline: CityTimeline) -> str | None:
    """session 裡的選取值若是現存建築或工地的 id 就原樣回傳，否則回 None（靜默清除）。"""
    if not isinstance(selected, str):
        return None
    valid = {building_id(holding_id=h.holding_id) for h in timeline.holdings}
    valid.add(SITE_ID)
    return selected if selected in valid else None


def build_specs(*, timeline: CityTimeline) -> tuple[CitySpec, ...]:
    """把進版位的項目與購屋工地轉為版位規格（分區、外形、名稱牌最寬參考文字）。"""
    specs = [
        CitySpec(
            id=building_id(holding_id=holding.holding_id),
            name=holding.name,
            zone=(zone := presentation.zone_for(kind=holding.kind, category=holding.category)),
            kind=holding.kind,
            shape=presentation.shape_for(zone=zone),
            peak=holding.peak_value,
            sub_reference=presentation.plate_sub(kind=holding.kind, value=holding.peak_value),
        )
        for holding in timeline.holdings
    ]
    specs.append(
        CitySpec(
            id=SITE_ID,
            name=CITY_TEXT.SITE_NAME,
            zone=CITY_ZONE.SITE,
            kind=SPEC_KIND_SITE,
            shape="",
            peak=0.0,
            sub_reference=presentation.site_sub(bucket_value=GEOMETRY.site_reference_amount),
        )
    )
    return tuple(specs)


def _cells(lot: Lot) -> set[tuple[int, int]]:
    i, j, width, depth = lot
    return {(a, b) for a in range(i, i + width) for b in range(j, j + depth)}


def _validated_lots(layout: CityLayout, expected_ids: Sequence[str]) -> dict[str, Lot]:
    """版位地塊必須涵蓋每個物件、不出地盤、互不重疊；違反屬程式錯誤。"""
    lots = dict(layout.lots)
    missing = [key for key in expected_ids if key not in lots]
    if missing:
        raise ValueError(f"版位缺少地塊：{missing}")
    occupied: set[tuple[int, int]] = set()
    for key in expected_ids:
        i, j, width, depth = lots[key]
        if i < 0 or j < 0 or i + width > layout.ground_i or j + depth > layout.ground_j:
            raise ValueError(f"地塊超出地盤：{key}")
        cells = _cells(lots[key])
        if cells & occupied:
            raise ValueError(f"地塊重疊：{key}")
        occupied |= cells
    return lots


def _plate(size: PlateSize) -> dict[str, object]:
    return {"w": size.width, "h": size.height, "lines": list(size.lines)}


def _building_entry(
    *,
    holding: CityHolding,
    state: CityBuildingState,
    lot: Lot,
    plate: PlateSize,
) -> dict[str, object]:
    present = state.status == CITY_BUILDING_STATUS.PRESENT and state.value is not None
    zone = presentation.zone_for(kind=holding.kind, category=holding.category)
    return {
        "id": building_id(holding_id=holding.holding_id),
        "name": holding.name,
        "zone": zone,
        "kind": holding.kind,
        "shape": presentation.shape_for(zone=zone),
        "lot": list(lot),
        "plate": _plate(plate),
        "value": state.value if present else 0,
        "vacant": not present,
        "plate_mode": _PLATE_MODE_BY_STATUS[state.status],
        "sub": presentation.plate_sub(kind=holding.kind, value=state.value) if present else "",
        "tip": list(presentation.building_tip(holding=holding, state=state)),
        "warn": present and state.drift is not None,
    }


def _site_entry(*, site: CitySite, lot: Lot, plate: PlateSize) -> dict[str, object]:
    met_by_key = {condition.key: condition.met for condition in site.checklist.conditions}
    if set(met_by_key) != set(HOUSE_TRIGGER.ALL):
        raise ValueError("購屋條件必須恰為五條")
    pct = site.progress.progress_pct
    progress = 0.0 if pct is None else min(1.0, max(0.0, pct / _PERCENT_DIVISOR))
    return {
        "id": SITE_ID,
        "name": CITY_TEXT.SITE_NAME,
        "lot": list(lot),
        "plate": _plate(plate),
        "progress": progress,
        "sub": presentation.site_sub(bucket_value=site.progress.bucket_value),
        "tip": list(presentation.site_tip(site=site)),
        "flags": [{"key": key, "met": met_by_key[key]} for key in HOUSE_TRIGGER.ALL],
    }


def build_payload(
    *, layout: CityLayout, timeline: CityTimeline, frame: CityFrame, selected: str | None
) -> dict[str, object]:
    """組成 JSON 可序列化的 payload。

    Args:
        layout: 版位結果。
        timeline: 整段歷史（提供項目順序與兩個高度分母）。
        frame: 選定月份的畫面資料，buildings 與 timeline.holdings 同順序、一對一。
        selected: 已驗證的選取 id；沒有選取為 None。

    Returns:
        前端契約字典。

    Raises:
        ValueError: 地塊缺漏、出地盤、重疊，或 frame 與 timeline 對不上。
    """
    if [s.holding_id for s in frame.buildings] != [h.holding_id for h in timeline.holdings]:
        raise ValueError("frame.buildings 與 timeline.holdings 不一致")
    building_ids = [building_id(holding_id=h.holding_id) for h in timeline.holdings]
    lots = _validated_lots(layout, [*building_ids, SITE_ID])
    plates = dict(layout.plates)
    weather = presentation.weather_display(status=frame.weather)
    return {
        "month": frame.year_month,
        "aria_label": CITY_TEXT.ARIA_LABEL,
        "ground": [layout.ground_i, layout.ground_j],
        "top_pad": float(layout.top_pad),
        "compact": layout.compact,
        "roads": [list(road) for road in layout.roads],
        "blocks": [list(block) for block in layout.blocks],
        "max_asset": timeline.max_asset_value,
        "max_liab": timeline.max_liability_value,
        "weather": {
            "sky": weather.sky,
            "severity": weather.severity,
            "title": weather.title,
            "subtitle": weather.subtitle,
        },
        "buildings": [
            _building_entry(holding=holding, state=state, lot=lots[key], plate=plates[key])
            for holding, state, key in zip(
                timeline.holdings, frame.buildings, building_ids, strict=True
            )
        ],
        "site": _site_entry(site=frame.site, lot=lots[SITE_ID], plate=plates[SITE_ID]),
        "selected": selected,
    }
