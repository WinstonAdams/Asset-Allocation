"""城市總覽的幾何常數與公式（純模組，無 I/O、不碰 streamlit）。

常數只有 `CityGeometry` 這一份，由 component 序列化後注入 city.js；投影、障礙物、名稱牌、
旗桿的公式與 city.js 各一份，docstring 標註對應的 JS 函式，方便並排審查。

幾何層的 kind 只分三種：`CITY_SHAPE.PIT`（負債坑洞）、`CITY_ZONE.SITE`（購屋工地），
其餘一律視為一般建築。
"""

# ==== 原生（標準庫） ====
import dataclasses
import json
import math

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.core.constants import CITY_SHAPE, CITY_ZONE

Point = tuple[float, float]
Rect = tuple[float, float, float, float]  # x0, y0, x1, y1
Lot = tuple[int, int, int, int]  # i, j, 寬, 深


@dataclasses.dataclass(frozen=True)
class CityGeometry:
    """與 city.js 共用的幾何常數；唯一來源，序列化後以 GEOM 前置注入 JS。"""

    tw: float = 64.0
    th: float = 32.0
    ux: float = 32.0
    vy: float = 16.0
    h_top: float = 176 * 0.92
    h_min: float = 8.0
    silo_roof: float = 18.0
    house_full: float = 64.0
    house_roof: float = 26.0
    crane_h: float = 150.0
    crane_l: float = 92.0
    crane_r: float = 26.0
    crane_hook: float = 52.0
    pad: float = 0.16
    pit_pad: float = 0.14
    flag_k: float = 0.8
    flag_du: float = 1.0
    flag_len: float = 0.48
    name_px: float = 11.0
    sub_px: float = 10.0
    line_gap: float = 2.0
    pad_l: float = 15.0
    pad_r: float = 6.0
    pad_y: float = 4.0
    name_max_w: float = 96.0
    lab_gap: float = 5.0
    side_m: float = 12.0
    top_m: float = 8.0
    bot_m: float = 8.0
    soil: float = 16.0
    narrow_w: float = 560.0
    overlay_h: float = 40.0
    sc_max: float = 1.15
    design_width: float = 818.0
    eps_px: float = 2.0
    site_reference_amount: int = 99_999_999
    margin: int = 1
    road: int = 2
    xgap: int = 4
    row_choices: tuple[int, ...] = (1, 2, 3)
    square_w: float = 0.4
    compact_n: int = 12
    pit_min_depth: float = 6.0
    pit_max_depth: float = 44.0


GEOMETRY = CityGeometry()

# 中日韓字元起點（CJK 部首補充區），之後的字元一律以全形估寬
_CJK_START = 0x2E80
# 旗桿列外框的版面常數（與 city.js flagGeom 同值）
_FLAG_FONT_MIN_SCALE = 0.62
_FLAG_POLE_MIN_H = 40.0
_FLAG_POLE_BASE_H = 72
_FLAG_FRONT_OFFSET = 0.2


def geometry_json() -> str:
    """GEOMETRY 的 JSON 字串（給 component 產生 `const GEOM = ...;` 前置行）。"""
    return json.dumps(dataclasses.asdict(GEOMETRY), sort_keys=True)


def project(*, i: float, j: float, scale: float) -> Point:
    """等角格點投影到螢幕座標（city.js `proj`）。"""
    return (
        (i - j) * GEOMETRY.ux * scale,
        (i + j) * GEOMETRY.vy * scale,
    )


def _lift(point: Point, z: float) -> Point:
    """螢幕座標往上抬 z px。"""
    return (point[0], point[1] - z)


def _ratio_sqrt(*, value: float, peak: float) -> float:
    """√(value ÷ peak)，value 小於 0 視為 0。"""
    return math.sqrt(max(value, 0) / peak)


def asset_height(*, value: float, max_asset: float) -> float:
    """建築高度：h_top × √(value ÷ max_asset)，下限 h_min；max_asset ≤ 0 時回 h_min。

    對應 city.js `assetHeight`。
    """
    if max_asset <= 0:
        return GEOMETRY.h_min
    return max(GEOMETRY.h_min, GEOMETRY.h_top * _ratio_sqrt(value=value, peak=max_asset))


def pit_depth(*, value: float, max_liability: float) -> float:
    """坑洞深度：pit_max_depth × √(value ÷ max_liability)，下限 pit_min_depth。

    分母是負債自己的歷史最高值，不與資產高度分母混用；max_liability ≤ 0 時回 pit_min_depth。
    對應 city.js `targetH`（負債分支）。
    """
    if max_liability <= 0:
        return GEOMETRY.pit_min_depth
    return max(
        GEOMETRY.pit_min_depth,
        GEOMETRY.pit_max_depth * _ratio_sqrt(value=value, peak=max_liability),
    )


def _char_em(ch: str) -> float:
    """單一字元的估計寬度（em）：中日韓全形最寬，標點最窄。"""
    if ord(ch) >= _CJK_START:
        return 1.0
    if ch in " .,":
        return 0.3
    if ch.isdigit():
        return 0.6
    if ch.isupper():
        return 0.72
    return 0.6


def text_width(*, text: str, px: float) -> float:
    """保守估算字寬（略大於實際）；前端實量若超過就縮字，所以底板尺寸一律以此為準。

    對應 city.js `textW`。
    """
    return sum(_char_em(c) for c in text) * px


def _fits(text: str) -> bool:
    """名稱單行是否放得進名稱牌最大寬度。"""
    return text_width(text=text, px=GEOMETRY.name_px) <= GEOMETRY.name_max_w


def wrap_name(*, name: str) -> tuple[str, ...]:
    """名稱最多折成兩行；過長時第二行以「…」截斷（city.js `wrapName`）。"""
    if _fits(name):
        return (name,)
    if " " in name:
        cut = name.rfind(" ", 0, len(name))
        first, second = name[:cut].rstrip(), name[cut + 1 :].lstrip()
        if _fits(first) and _fits(second):
            return (first, second)
    cut = next((k for k in range(len(name), 0, -1) if _fits(name[:k])), 1)
    rest = name[cut:].lstrip()
    while rest and not _fits(rest):
        rest = rest[:-2] + "…"
    if rest:
        return (name[:cut].rstrip(), rest)
    return (name[:cut],)


def plate_size(*, lines: tuple[str, ...], sub: str | None) -> tuple[int, int]:
    """名稱牌寬高（px）；sub 為 None 時是只有名稱的精簡牌（city.js `plateSize`）。"""
    subs = [] if sub is None else [sub]
    widest = max(
        [text_width(text=t, px=GEOMETRY.name_px) for t in lines]
        + [text_width(text=t, px=GEOMETRY.sub_px) for t in subs]
    )
    width = widest + GEOMETRY.pad_l + GEOMETRY.pad_r
    height = (
        GEOMETRY.name_px * len(lines)
        + GEOMETRY.sub_px * len(subs)
        + GEOMETRY.line_gap * (len(lines) + len(subs) - 1)
        + 2 * GEOMETRY.pad_y
    )
    return math.ceil(width), int(height)


def flag_rect(*, lot: Lot, scale: float) -> Rect:
    """五根旗桿列的外框，位於工地前緣正前方（city.js `flagGeom`、`drawFlags`）。"""
    i, j, w, d = lot
    font_scale = max(scale, _FLAG_FONT_MIN_SCALE)
    pole_h = GEOMETRY.flag_k * max(_FLAG_POLE_MIN_H, _FLAG_POLE_BASE_H * scale)
    front = i + j + w + d + _FLAG_FRONT_OFFSET
    center = (i + w / 2) - (j + d / 2)
    xs = [
        project(i=(front + u) / 2, j=(front - u) / 2, scale=scale)[0]
        for u in (center - 2 * GEOMETRY.flag_du, center + 2 * GEOMETRY.flag_du)
    ]
    y = front * GEOMETRY.vy * scale
    return (
        xs[0] - GEOMETRY.flag_len * GEOMETRY.ux * scale - 2,
        y
        - pole_h
        - GEOMETRY.flag_len * GEOMETRY.vy * scale
        - 2.6 * font_scale * GEOMETRY.flag_k
        - 2.4 * font_scale
        - 2,
        xs[1] + 8 * font_scale + 1,
        y + 2 + 2.4 * font_scale,
    )


def plate_rect(*, kind: str, lot: Lot, width: float, height: float, scale: float) -> Rect:
    """名稱牌外框：水平置中於地塊中心，頂邊在底座前緣下 lab_gap（工地則在旗桿列之下）。

    對應 city.js `plateRect`。
    """
    i, j, w, d = lot
    pad = {CITY_SHAPE.PIT: GEOMETRY.pit_pad, CITY_ZONE.SITE: 0.0}.get(kind, GEOMETRY.pad)
    cx = project(i=i + w / 2, j=j + d / 2, scale=scale)[0]
    top = project(i=i + w - pad, j=j + d - pad, scale=scale)[1] + GEOMETRY.lab_gap
    if kind == CITY_ZONE.SITE:
        top = flag_rect(lot=lot, scale=scale)[3] + 2
    return (cx - width / 2, top, cx + width / 2, top + height)


def _pit_obstacles(lot: Lot, scale: float) -> list[tuple[str, list[Point]]]:
    i, j, w, d = lot
    a = GEOMETRY.pit_pad
    quad = [
        project(i=i + a, j=j + a, scale=scale),
        project(i=i + w - a, j=j + a, scale=scale),
        project(i=i + w - a, j=j + d - a, scale=scale),
        project(i=i + a, j=j + d - a, scale=scale),
    ]
    return [(CITY_SHAPE.PIT, quad)]


def _site_obstacles(lot: Lot, scale: float) -> list[tuple[str, list[Point]]]:
    i, j, w, d = lot
    full = GEOMETRY.house_full * scale
    footprint = [
        project(i=i, j=j, scale=scale),
        project(i=i + w, j=j, scale=scale),
        project(i=i + w, j=j + d, scale=scale),
        project(i=i, j=j + d, scale=scale),
    ]
    apex = _lift(
        project(i=i + w / 2, j=j + d / 2, scale=scale),
        (GEOMETRY.house_full + GEOMETRY.house_roof) * scale,
    )
    root = project(i=i + w - 0.15, j=j + 0.25, scale=scale)
    top = _lift(root, GEOMETRY.crane_h * scale)
    left = top[0] - GEOMETRY.crane_l * scale
    right = top[0] + GEOMETRY.crane_r * scale
    mast = [root, (root[0] - 3, root[1]), top, (top[0] + 3, top[1])]
    arm = [
        (left, top[1] + 6 * scale),
        (right, top[1] + 2 * scale),
        (right, top[1] - 3),
        (left, top[1] + GEOMETRY.crane_hook * scale),
    ]
    x0, y0, x1, y1 = flag_rect(lot=lot, scale=scale)
    return [
        (CITY_ZONE.SITE, footprint + [_lift(p, full) for p in footprint] + [apex]),
        ("crane", mast),
        ("crane", arm),
        ("flags", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]),
    ]


def obstacles(
    *, kind: str, lot: Lot, height: float, roof: float, scale: float
) -> list[tuple[str, list[Point]]]:
    """名稱牌不可碰的形狀（city.js `obstacles`）；地面陰影不是建築，不列入。"""
    if kind == CITY_SHAPE.PIT:
        return _pit_obstacles(lot, scale)
    if kind == CITY_ZONE.SITE:
        return _site_obstacles(lot, scale)
    i, j, w, d = lot
    lift = height * scale
    pad = GEOMETRY.pad
    a = project(i=i + pad, j=j + pad, scale=scale)
    b = project(i=i + w - pad, j=j + pad, scale=scale)
    c = project(i=i + w - pad, j=j + d - pad, scale=scale)
    e = project(i=i + pad, j=j + d - pad, scale=scale)
    points = [_lift(a, lift), _lift(b, lift), b, c, e, _lift(e, lift)]
    if roof:
        center = project(i=i + w / 2, j=j + d / 2, scale=scale)
        points.append(_lift(center, lift + roof * scale))
    return [("building", points)]


def fit_scale(*, ground_i: int, ground_j: int, canvas_w: float) -> float:
    """整塊菱形地盤塞進畫布寬度的縮放，上限 sc_max（city.js `fitScale`）。"""
    usable = canvas_w - 2 * GEOMETRY.side_m
    return min(GEOMETRY.sc_max, usable / ((ground_i + ground_j) * GEOMETRY.ux))
