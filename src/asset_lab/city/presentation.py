"""城市呈現（純模組，不碰 st.*）：分區外形、金額文字、天氣、小卡內容。

小卡文案一律取自 CITY_TEXT；是否加「依目前設定判定」由 CityFrame.is_latest 決定。
"""

# ==== 原生（標準庫） ====
from dataclasses import dataclass

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import (
    CITY_AMOUNT,
    CITY_BUILDING_STATUS,
    CITY_SHAPE,
    CITY_TEXT,
    CITY_WEATHER,
    CITY_ZONE,
    HOLDING_KIND,
    HOUSE_TRIGGER,
    PROTOCOL_LEVELS,
)
from asset_lab.models.results import (
    CityBuildingState,
    CityFrame,
    CityHolding,
    CitySite,
    ProtocolStatus,
)
from asset_lab.overview_presentation import resolve_presentation

_LEVEL_LABEL = {spec.code: spec.label for spec in PROTOCOL_LEVELS}
_PERCENT_MULTIPLIER = 100


@dataclass(frozen=True)
class CityWeatherDisplay:
    sky: str
    severity: str
    title: str
    subtitle: str


@dataclass(frozen=True)
class CityCard:
    title: str
    rows: tuple[tuple[str, str], ...]
    notes: tuple[str, ...]


def zone_for(*, kind: str, category: str | None) -> str:
    """項目的分區鍵；負債一律歸負債分區，資產依類別查表。"""
    if kind == HOLDING_KIND.LIABILITY:
        return CITY_ZONE.LIABILITY
    return CITY_ZONE.BY_CATEGORY[category]


def shape_for(*, zone: str) -> str:
    """分區的建築外形鍵；工地沒有外形，回空字串。"""
    return CITY_SHAPE.BY_ZONE.get(zone, "")


def amount_text(*, value: float) -> str:
    """金額以萬為單位、千分位、一位小數，例如「1,234.5 萬」。"""
    return f"{value / CITY_AMOUNT.DIVISOR:,.1f} {CITY_AMOUNT.UNIT}"


def plate_sub(*, kind: str, value: float) -> str:
    """名稱牌第二行；負債加「應繳」前綴。"""
    text = amount_text(value=value)
    if kind == HOLDING_KIND.LIABILITY:
        return f"{CITY_TEXT.LIABILITY_PREFIX} {text}"
    return text


def site_sub(*, bucket_value: float) -> str:
    """工地名稱牌第二行。"""
    return f"{CITY_TEXT.SITE_AMOUNT_PREFIX} {amount_text(value=bucket_value)}"


def weather_display(*, status: ProtocolStatus) -> CityWeatherDisplay:
    """協定判定結果轉天氣面板；資料不足時用中性呈現與現行資料不足文案。"""
    presentation = resolve_presentation(status)
    if presentation.neutral_message is not None:
        spec = CITY_WEATHER.NEUTRAL
        return CityWeatherDisplay(
            sky=spec.sky,
            severity=spec.severity,
            title=spec.name,
            subtitle=presentation.neutral_message,
        )
    spec = CITY_WEATHER.BY_LEVEL[status.level_code]
    depth = abs(presentation.drawdown_percent or 0.0)
    return CityWeatherDisplay(
        sky=spec.sky,
        severity=spec.severity,
        title=f"{spec.name}・{status.level_code} {_LEVEL_LABEL[status.level_code]}",
        subtitle=CITY_TEXT.DRAWDOWN.format(pct=f"{depth:.1f}%"),
    )


def _compare_text(*, state: CityBuildingState) -> str | None:
    """與前一月相比的文字；最早月份不顯示。"""
    if state.previous_month is None:
        return None
    if state.previous_status == CITY_BUILDING_STATUS.ABSENT:
        return CITY_TEXT.PREVIOUS_ABSENT.format(month=state.previous_month)
    if state.previous_status == CITY_BUILDING_STATUS.UNFILLED:
        return CITY_TEXT.PREVIOUS_UNFILLED.format(month=state.previous_month)
    if state.delta is None:
        return None
    if state.delta > 0:
        change = CITY_TEXT.CARD_DELTA_UP.format(amount=amount_text(value=state.delta))
    elif state.delta < 0:
        change = CITY_TEXT.CARD_DELTA_DOWN.format(amount=amount_text(value=-state.delta))
    else:
        change = CITY_TEXT.CARD_DELTA_FLAT
    return f"{CITY_TEXT.COMPARE_WITH.format(month=state.previous_month)} {change}"


def building_tip(*, holding: CityHolding, state: CityBuildingState) -> tuple[str, ...]:
    """建築 hover 提示；未填月份不畫建築，也沒有提示。"""
    if state.status == CITY_BUILDING_STATUS.UNFILLED:
        return ()
    if state.status == CITY_BUILDING_STATUS.ABSENT or state.value is None:
        return (holding.name, CITY_TEXT.ABSENT)
    lines = [holding.name, plate_sub(kind=holding.kind, value=state.value)]
    compare = _compare_text(state=state)
    if compare is not None:
        lines.append(compare)
    return tuple(lines)


def site_tip(*, site: CitySite) -> tuple[str, ...]:
    """工地 hover 提示。"""
    checklist = site.checklist
    return (
        CITY_TEXT.SITE_NAME,
        site_sub(bucket_value=site.progress.bucket_value),
        CITY_TEXT.SITE_CONDITIONS.format(met=checklist.met_count, total=len(checklist.conditions)),
    )


def building_card(*, holding: CityHolding, state: CityBuildingState, frame: CityFrame) -> CityCard:
    """建築小卡：名稱、類別、該月市值、與前一月相比，另依狀態與月份加註記。"""
    category = (
        CITY_ZONE.ZONE_LABEL[CITY_ZONE.DEBT]
        if holding.kind == HOLDING_KIND.LIABILITY
        else holding.category or ""
    )
    rows: list[tuple[str, str]] = [(CITY_TEXT.CARD_LABEL_CATEGORY, category)]
    notes: list[str] = []
    if state.status == CITY_BUILDING_STATUS.UNFILLED:
        notes.append(CITY_TEXT.UNFILLED)
    elif state.status == CITY_BUILDING_STATUS.ABSENT or state.value is None:
        notes.append(CITY_TEXT.ABSENT)
    else:
        rows.append((CITY_TEXT.CARD_LABEL_VALUE, amount_text(value=state.value)))
        compare = _compare_text(state=state)
        if compare is not None:
            rows.append((CITY_TEXT.CARD_LABEL_COMPARE, compare))
        if state.drift is not None:
            drift = state.drift
            rows.append(
                (
                    CITY_TEXT.CARD_LABEL_DRIFT,
                    CITY_TEXT.CARD_DRIFT_VALUE.format(
                        current=f"{drift.current_weight:.1f}",
                        target=f"{drift.target_weight:.1f}",
                        drift=f"{drift.drift:+.1f}",
                    ),
                )
            )
            if not frame.is_latest:
                notes.append(CITY_TEXT.BY_CURRENT_SETTINGS)
            if holding.category in frame.house_purpose_categories:
                notes.append(CITY_TEXT.INCLUDES_HOUSE_PURPOSE)
    return CityCard(title=holding.name, rows=tuple(rows), notes=tuple(notes))


def site_card(*, site: CitySite, is_latest: bool) -> CityCard:
    """工地小卡：自備款、目標、進度與五條條件；不含以今天計算的達標年數與每年累積額。"""
    progress = site.progress
    rows: list[tuple[str, str]] = [
        (CITY_TEXT.CARD_LABEL_SITE_AMOUNT, amount_text(value=progress.bucket_value))
    ]
    if progress.target_amount <= 0 or progress.progress_pct is None:
        rows.append((CITY_TEXT.CARD_LABEL_SITE_TARGET, CITY_TEXT.TARGET_UNSET))
    else:
        rows.append((CITY_TEXT.CARD_LABEL_SITE_TARGET, amount_text(value=progress.target_amount)))
        rows.append((CITY_TEXT.CARD_LABEL_SITE_PROGRESS, f"{progress.progress_pct:.0f}%"))
    for condition in site.checklist.conditions:
        rows.append(
            (
                HOUSE_TRIGGER.LABEL[condition.key],
                CITY_TEXT.MET if condition.met else CITY_TEXT.NOT_MET,
            )
        )
    notes = () if is_latest else (CITY_TEXT.BY_CURRENT_SETTINGS,)
    return CityCard(title=CITY_TEXT.SITE_NAME, rows=tuple(rows), notes=notes)
