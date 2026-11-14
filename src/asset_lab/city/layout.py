"""城市版位（純模組，無 I/O、不碰 streamlit）：確定性、不搜尋的沿街長條街廓排版。

骨架
- 建築排在「列」上：列沿 j 軸（螢幕往左下）延伸、沿 i 軸由後往前疊；高的類別排後面。
- 一個分區＝一塊街廓；街廓之間是沿格線的道路。
- 名稱牌固定在建築底座前緣正下方，只可能被「前方」的東西擋到，所以版位只需兩條規則：
  1. 同列間距：下一棟（左下方）連同工地旗桿，都要落在上一棟名稱牌之外，名稱牌彼此不重疊。
  2. 列距：前方各列（含吊車、旗桿）都要低於名稱牌底；由最前列往後逐列取最小可行列距。
- 縮放只有一個：整塊菱形地盤塞進畫布寬；名稱牌是固定 px，比例越大越安全，
  所以設計寬度算出的版位在更寬的畫布上一定仍成立。
- 版位用歷史最高市值算（高度只會比它矮），月與月之間不動。
- 候選參數是一個整數（街帶長度上限的分段），全部算一遍取「縮放 ×（1 − 長寬差懲罰）」最高者。
"""

# ==== 原生（標準庫） ====
import dataclasses
import functools
import math
from collections.abc import Sequence

# ==== 第三方套件 ====
# 無
# ==== 專案內部 ====
from asset_lab.city import geometry
from asset_lab.city.geometry import GEOMETRY, Lot, Point, Rect
from asset_lab.core.constants import CITY_SHAPE, CITY_TEXT, CITY_ZONE
from asset_lab.core.exceptions import CityLayoutError

Shape = tuple[str, list[Point], Rect]  # 障礙物種類、凸包、外框

SPEC_KIND_ASSET = "asset"
SPEC_KIND_LIABILITY = "liability"
SPEC_KIND_SITE = "site"

# 內部物件分三種幾何類型：一般建築、負債坑洞（CITY_SHAPE.PIT）、購屋工地（CITY_ZONE.SITE）
_KIND_BUILDING = "building"

# 類別最高點相同時的排序依據：越前面越靠後排
_ZONE_TIE_ORDER = (
    CITY_ZONE.STOCK,
    CITY_ZONE.DEPOSIT,
    CITY_ZONE.CASH,
    CITY_ZONE.SITE,
    CITY_ZONE.INSURANCE,
    CITY_ZONE.DEBT,
)
_UNKNOWN_ZONE_RANK = 9

# 固定點迭代：起始縮放、最大輪數、第幾輪開始以保守係數收斂
_INITIAL_SCALE = 0.7
_MAX_ITERATIONS = 16
_DAMPING_FROM = 8
_DAMPING_FACTOR = 0.97
_CANDIDATE_COUNT = 12
_SCALE_TOLERANCE = 1e-9
# 地盤邊界外留一點空間，避免名稱牌貼著地盤邊線
_GROUND_SLACK = 0.3
# 只含兩格地塊的建築貼齊後，同類相鄰欄的最小間距：地塊 2 格＋至少 1 格空地
_SAME_ZONE_COLUMN_STEP = 3


@dataclasses.dataclass(frozen=True)
class CitySpec:
    """一個版位物件：建築、坑洞或工地。"""

    id: str
    name: str
    zone: str
    kind: str  # SPEC_KIND_*
    shape: str  # CITY_SHAPE；工地為空字串
    peak: float  # 版位高度依據；工地不用
    sub_reference: str | None  # 名稱牌第二行可能出現的最寬文字


@dataclasses.dataclass(frozen=True)
class PlateSize:
    """名稱牌尺寸（px，與縮放無關）。"""

    width: int
    height: int
    lines: tuple[str, ...]  # 名稱各行（第二行市值由 payload 每月提供）


@dataclasses.dataclass(frozen=True)
class CityLayout:
    """版位結果；座標單位是格點，scale 為設計寬度下的縮放。"""

    scale: float
    ground_i: int
    ground_j: int
    top_pad: float  # 地盤頂點以上要留的高度（scale=1 的 px）
    lots: tuple[tuple[str, Lot], ...]
    plates: tuple[tuple[str, PlateSize], ...]
    roads: tuple[tuple[int, int, int, int, str], ...]  # i0, i1, j0, j1, "i" | "j"
    blocks: tuple[tuple[str, int, int, int, int], ...]  # zone, i0, i1, j0, j1
    compact: bool  # 物件數超過 compact_n：名稱牌只放名稱


# ---------------------------------------------------------------- 排版內部物件
@dataclasses.dataclass(frozen=True)
class _Obj:
    id: str
    zone: str
    kind: str
    height: float
    roof: float
    plate_w: int
    plate_h: int

    @property
    def row_offset(self) -> int:
        """坑洞（1×1）貼在列的前排。"""
        return 1 if self.kind == CITY_SHAPE.PIT else 0

    @property
    def size(self) -> int:
        return 1 if self.kind == CITY_SHAPE.PIT else 2

    def lot(self, row_i: int, j: int) -> Lot:
        return (row_i + self.row_offset, j, self.size, self.size)


@dataclasses.dataclass(frozen=True)
class _Proto:
    """物件在 (列 0, j 0) 時的障礙形狀與名稱牌；實際位置只是平移。"""

    obj: _Obj
    shapes: list[Shape]
    plate: Rect
    top: float  # 形狀最高點 y
    flags: Rect | None


@dataclasses.dataclass
class _Draft:
    rows: list[list[tuple[_Proto, int]]]
    row_i: list[int]
    ground_i: int
    ground_j: int
    roads: list[tuple[int, int, int, int, str]]
    blocks: list[tuple[str, int, int, int, int]]


Spacing = dict[tuple[_Obj, _Obj, float, int], int]  # 同列間距 memo：只存在於單次排版
Band = tuple[
    list[list[tuple[_Proto, int]]],
    list[tuple[str, int, int]],
]


# ---------------------------------------------------------------- 平面幾何
def _bbox(points: Sequence[Point]) -> Rect:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _hull(points: Sequence[Point]) -> list[Point]:
    """凸包（Andrew monotone chain）。"""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts
    lower: list[Point] = []
    for q in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list[Point] = []
    for q in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return lower[:-1] + upper[:-1]


def _separating_axis(rect: Rect, hull: Sequence[Point]) -> bool:
    """矩形與凸包是否相交（分離軸）。"""
    x0, y0, x1, y1 = rect
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for k in range(len(hull)):
        a, b = hull[k], hull[(k + 1) % len(hull)]
        nx, ny = b[1] - a[1], a[0] - b[0]
        hull_proj = [q[0] * nx + q[1] * ny for q in hull]
        rect_proj = [q[0] * nx + q[1] * ny for q in corners]
        if max(hull_proj) < min(rect_proj) or max(rect_proj) < min(hull_proj):
            return False
    return True


def _rect_hits_polygon(rect: Rect, polygon: Sequence[Point]) -> bool:
    x0, y0, x1, y1 = rect
    if max(p[0] for p in polygon) < x0 or min(p[0] for p in polygon) > x1:
        return False
    if max(p[1] for p in polygon) < y0 or min(p[1] for p in polygon) > y1:
        return False
    return _separating_axis(rect, _hull(polygon))


def _rects_hit(a: Rect, b: Rect, margin: float = 0.0) -> bool:
    return not (
        a[2] + margin <= b[0]
        or b[2] + margin <= a[0]
        or a[3] + margin <= b[1]
        or b[3] + margin <= a[1]
    )


def _shift(rect: Rect, dx: float, dy: float) -> Rect:
    return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)


def _plate_hits_shapes(plate: Rect, shapes: list[Shape], dx: float, dy: float) -> bool:
    """名稱牌（固定）是否碰到平移 (dx, dy) 後的形狀：反向平移名稱牌，避免複製頂點。"""
    m = GEOMETRY.eps_px
    probe = (plate[0] - m - dx, plate[1] - m - dy, plate[2] + m - dx, plate[3] + m - dy)
    for _kind, hull, box in shapes:
        if box[2] < probe[0] or box[0] > probe[2] or box[3] < probe[1] or box[1] > probe[3]:
            continue
        if _separating_axis(probe, hull):
            return True
    return False


# ---------------------------------------------------------------- 原型：原點算一次，之後只平移
def _proto(obj: _Obj, scale: float) -> _Proto:
    lot = obj.lot(0, 0)
    shapes: list[Shape] = []
    for kind, points in geometry.obstacles(
        kind=obj.kind, lot=lot, height=obj.height, roof=obj.roof, scale=scale
    ):
        hull = _hull(points)
        shapes.append((kind, hull, _bbox(hull)))
    flags = geometry.flag_rect(lot=lot, scale=scale) if obj.kind == CITY_ZONE.SITE else None
    return _Proto(
        obj=obj,
        shapes=shapes,
        plate=geometry.plate_rect(
            kind=obj.kind, lot=lot, width=obj.plate_w, height=obj.plate_h, scale=scale
        ),
        top=min(s[2][1] for s in shapes),
        flags=flags,
    )


def _offset(i: float, j: float, scale: float) -> Point:
    return geometry.project(i=i, j=j, scale=scale)


# ---------------------------------------------------------------- 規則 1：同列間距
def _next_j(a: _Proto, a_j: int, b: _Proto, scale: float, gap: int, memo: Spacing) -> int:
    """b 排在 a 的左下方（同一列、j 較大）時的最小 j。"""
    key = (a.obj, b.obj, scale, gap)
    spacing = memo.get(key)
    if spacing is None:
        spacing = memo[key] = _min_spacing(a, b, scale, gap)
    return a_j + spacing


def _min_spacing(a: _Proto, b: _Proto, scale: float, gap: int) -> int:
    j = a.obj.size + gap
    while True:
        dx, dy = _offset(0, j, scale)
        b_plate = _shift(b.plate, dx, dy)
        blocked = (
            _plate_hits_shapes(a.plate, b.shapes, dx, dy)
            or _plate_hits_shapes(b_plate, a.shapes, 0, 0)
            or _rects_hit(a.plate, b_plate, GEOMETRY.eps_px)
        )
        if not blocked:
            return j
        j += 1


def _place_band(
    zones: list[list[_Proto]], nrows: int, scale: float, gap: int, memo: Spacing
) -> Band:
    """一條街帶（nrows 列）內依序排各類別方塊：同欄所有列共用 j；方塊內由高到矮逐列填。"""
    rows: list[list[tuple[_Proto, int]]] = [[] for _ in range(nrows)]
    spans: list[tuple[str, int, int]] = []
    last: list[tuple[_Proto, int] | None] = [None] * nrows
    end = GEOMETRY.margin - gap
    for zone in zones:
        columns = max(1, math.ceil(len(zone) / nrows))
        start: int | None = None
        col_j = 0
        for t in range(columns):
            first = t == 0
            j = max(GEOMETRY.margin, end + gap) if first else col_j + _SAME_ZONE_COLUMN_STEP
            for r in range(nrows):
                k = r * columns + t
                prev = last[r]
                if k < len(zone) and prev is not None:
                    j = max(j, _next_j(prev[0], prev[1], zone[k], scale, gap if first else 1, memo))
            for r in range(nrows):
                k = r * columns + t
                if k < len(zone):
                    rows[r].append((zone[k], j))
                    last[r] = (zone[k], j)
            col_j = j
            start = j if start is None else start
        end = max(x[1] + x[0].obj.size for x in last if x)
        spans.append((zone[0].obj.zone, start if start is not None else end, end))
    return rows, spans


# ---------------------------------------------------------------- 規則 2：列距
def _row_offsets(
    rows: Sequence[Sequence[tuple[_Proto, int]]], scale: float, minimums: Sequence[int]
) -> list[int]:
    count = len(rows)
    plates = [[_shift(p.plate, *_offset(0, j, scale)) for p, j in row] for row in rows]
    bottoms = [max((r[3] for r in pl), default=-1e9) for pl in plates]
    rel = [0] * count  # 各列相對最前列的 i（往後為負）
    for r in range(count - 2, -1, -1):
        distance = minimums[r]
        while _row_conflict(r, rows, plates, bottoms[r], rel, rel[r + 1] - distance, scale):
            distance += 1
        rel[r] = rel[r + 1] - distance
    return [x - rel[0] for x in rel]


def _row_conflict(
    r: int,
    rows: Sequence[Sequence[tuple[_Proto, int]]],
    plates: Sequence[Sequence[Rect]],
    bottom: float,
    rel: Sequence[int],
    base: int,
    scale: float,
) -> bool:
    for s in range(r + 1, len(rows)):
        di = rel[s] - base
        for proto, j in rows[s]:
            dx, dy = _offset(di, j, scale)
            if proto.top + dy > bottom + GEOMETRY.eps_px:
                continue  # 這棟最高點已在本列名稱牌之下
            moved = _shift(proto.plate, dx, dy)
            for plate in plates[r]:
                if _plate_hits_shapes(plate, proto.shapes, dx, dy):
                    return True
                if _rects_hit(plate, moved, GEOMETRY.eps_px):
                    return True
    return False


# ---------------------------------------------------------------- 分組與高度排序
def _build_objects(specs: Sequence[CitySpec], max_asset: float, compact: bool) -> list[_Obj]:
    out: list[_Obj] = []
    for spec in specs:
        lines = geometry.wrap_name(name=spec.name)
        sub = None if compact else spec.sub_reference
        plate_w, plate_h = geometry.plate_size(lines=lines, sub=sub)
        if spec.kind == SPEC_KIND_SITE:
            out.append(
                _Obj(
                    spec.id,
                    spec.zone,
                    CITY_ZONE.SITE,
                    GEOMETRY.house_full,
                    GEOMETRY.house_roof,
                    plate_w,
                    plate_h,
                )
            )
        elif spec.kind == SPEC_KIND_LIABILITY:
            out.append(_Obj(spec.id, spec.zone, CITY_SHAPE.PIT, 0.0, 0.0, plate_w, plate_h))
        else:
            roof = GEOMETRY.silo_roof if spec.shape == CITY_SHAPE.SILO else 0.0
            height = geometry.asset_height(value=spec.peak, max_asset=max_asset)
            out.append(_Obj(spec.id, spec.zone, _KIND_BUILDING, height, roof, plate_w, plate_h))
    return out


def _group_by_zone(objs: Sequence[_Obj]) -> list[list[_Obj]]:
    """類別依「最高那棟」由高到矮排序；類別內由高到矮（同高依 id，結果確定）。"""
    tops = {o.id: -_proto(o, 1.0).top for o in objs}
    by_zone: dict[str, list[_Obj]] = {}
    for obj in objs:
        by_zone.setdefault(obj.zone, []).append(obj)
    groups = [sorted(v, key=lambda o: (-tops[o.id], o.id)) for v in by_zone.values()]
    rank = {zone: k for k, zone in enumerate(_ZONE_TIE_ORDER)}
    return sorted(
        groups,
        key=lambda g: (-tops[g[0].id], rank.get(g[0].zone, _UNKNOWN_ZONE_RANK), g[0].zone),
    )


# ---------------------------------------------------------------- 方案組裝
def _extent(
    rows: Sequence[Sequence[tuple[_Proto, int]]], row_i: Sequence[int], scale: float
) -> tuple[int, int]:
    """地塊、名稱牌、旗桿都要在地盤內：回傳最小 (ground_i, ground_j)。"""
    max_i = max_j = 0.0
    ux, vy = GEOMETRY.ux * scale, GEOMETRY.vy * scale
    for r, row in enumerate(rows):
        for proto, j in row:
            i0, j0, w, d = proto.obj.lot(row_i[r], j)
            max_i, max_j = max(max_i, i0 + w), max(max_j, j0 + d)
            dx, dy = _offset(row_i[r], j, scale)
            boxes = [proto.plate] + ([proto.flags] if proto.flags else [])
            for x0, _y0, x1, y1 in boxes:
                for x in (x0 + dx, x1 + dx):
                    u, v = x / ux, (y1 + dy) / vy
                    max_i, max_j = max(max_i, (v + u) / 2), max(max_j, (v - u) / 2)
    return math.ceil(max_i + _GROUND_SLACK), math.ceil(max_j + _GROUND_SLACK)


def _justify(
    rows: list[list[tuple[_Proto, int]]], spans: list[tuple[str, int, int]], target: int
) -> Band:
    """街帶比最長的短時，把多出的格數平均分到頭、各類別之間、尾的空地（像文字左右對齊）。"""
    extra = target - spans[-1][2] if spans else 0
    if extra <= 0:
        return rows, spans
    slots = len(spans) + 1
    add = [extra // slots + (1 if m < extra % slots else 0) for m in range(slots)]
    shift: dict[str, int] = {}
    acc = 0
    out: list[tuple[str, int, int]] = []
    for m, (zone, a, b) in enumerate(spans):
        acc += add[m]
        shift[zone] = acc
        out.append((zone, a + acc, b + acc))
    return [[(p, j + shift[p.obj.zone]) for p, j in row] for row in rows], out


def _bands_to_draft(bands: Sequence[Band], scale: float) -> _Draft:
    """相鄰街帶之間是大道（沿 j），街帶內列間是中庭。"""
    margin, road = GEOMETRY.margin, GEOMETRY.road
    rows: list[list[tuple[_Proto, int]]] = []
    band_of: list[int] = []
    for bi, (band_rows, _spans) in enumerate(bands):
        for row in band_rows:
            if row:
                rows.append(row)
                band_of.append(bi)
    minimums = [2 + (road + 1 if band_of[k + 1] != band_of[k] else 1) for k in range(len(rows) - 1)]
    rel = _row_offsets(rows, scale, [*minimums, 0])
    row_i = [margin + x for x in rel]
    ground_i, ground_j = _extent(rows, row_i, scale)
    ground_i = max(ground_i, row_i[-1] + 2 + margin)
    ends = [end for _r, spans in bands for _z, _s, end in spans]
    ground_j = max(ground_j, max(ends) + margin)

    roads: list[tuple[int, int, int, int, str]] = []
    blocks: list[tuple[str, int, int, int, int]] = []
    band_i: list[tuple[int, int]] = []
    for bi in range(len(bands)):
        ks = [k for k in range(len(rows)) if band_of[k] == bi]
        i0 = 0 if bi == 0 else band_i[-1][1] + road
        i1 = ground_i if bi == len(bands) - 1 else row_i[ks[-1]] + 2
        band_i.append((i0, i1))
        if bi < len(bands) - 1:
            # 大道緊貼街帶前緣：名稱牌掛在大道上
            roads.append((i1, i1 + road, 0, ground_j, "j"))
    for bi, (_rows, spans) in enumerate(bands):
        i0, i1 = band_i[bi]
        cuts = [
            spans[k][2] + (spans[k + 1][1] - spans[k][2] - road) // 2 for k in range(len(spans) - 1)
        ]
        for k, (zone, _s, _e) in enumerate(spans):
            left = 0 if k == 0 else cuts[k - 1] + road
            right = ground_j if k == len(spans) - 1 else cuts[k]
            if k + 1 < len(spans):
                roads.append((i0, i1, cuts[k], cuts[k] + road, "i"))
            blocks.append((zone, i0, i1, left, right))
    return _Draft(rows, row_i, ground_i, ground_j, roads, blocks)


def _band_end(zones: list[list[_Proto]], nrows: int, scale: float, memo: Spacing) -> int:
    return _place_band(zones, nrows, scale, GEOMETRY.xgap, memo)[1][-1][2]


def _fit_rows(
    zones: list[list[_Proto]],
    scale: float,
    limit: int,
    memo: Spacing,
    choices: Sequence[int] = (1,),
) -> int | None:
    return next((n for n in choices if _band_end(zones, n, scale, memo) <= limit), None)


def _draft_with_limit(
    groups: list[list[_Proto]], scale: float, limit: int, memo: Spacing
) -> _Draft:
    """街帶長度上限 limit 格：類別依高度順序逐條街帶填入（next-fit，不回頭）；
    每條街帶取「放得進 limit 的最少列數」，放不下才換下一條。"""
    bands: list[tuple[list[list[_Proto]], int]] = []
    for group in groups:
        if bands and bands[-1][1] == 1 and _fit_rows(bands[-1][0] + [group], scale, limit, memo):
            bands[-1] = (bands[-1][0] + [group], 1)
            continue
        rows = _fit_rows([group], scale, limit, memo, GEOMETRY.row_choices)
        bands.append(([group], rows or GEOMETRY.row_choices[-1]))
    placed = [_place_band(zs, n, scale, GEOMETRY.xgap, memo) for zs, n in bands]
    target = max(spans[-1][2] for _r, spans in placed)
    return _bands_to_draft([_justify(rows, spans, target) for rows, spans in placed], scale)


def _draft_for_candidate(
    groups: list[list[_Proto]], scale: float, candidate: int, memo: Spacing
) -> _Draft:
    """街帶長度上限取「單條街帶全長」的第 candidate/(n-1) 段。"""
    low = max(_band_end([g], 1, scale, memo) for g in groups)
    low = min(low, max(_band_end([g], 2, scale, memo) for g in groups) + 4)
    high = max(low, _band_end(groups, 1, scale, memo))
    limit = low + round((high - low) * candidate / (_CANDIDATE_COUNT - 1))
    return _draft_with_limit(groups, scale, limit, memo)


def _solve(group_objs: list[list[_Obj]]) -> tuple[float, _Draft]:
    """在假設縮放下排出地盤 → 算實際縮放 → 若比假設小就以實際值重排（通常 2–5 輪收斂）。"""
    scale = _INITIAL_SCALE
    canvas_w = GEOMETRY.design_width
    memo: Spacing = {}
    for it in range(_MAX_ITERATIONS):
        groups = [[_proto(o, scale) for o in g] for g in group_objs]
        scored: list[tuple[float, float, _Draft]] = []
        for candidate in range(_CANDIDATE_COUNT):
            draft = _draft_for_candidate(groups, scale, candidate, memo)
            fitted = geometry.fit_scale(
                ground_i=draft.ground_i, ground_j=draft.ground_j, canvas_w=canvas_w
            )
            skew = abs(draft.ground_i - draft.ground_j) / (draft.ground_i + draft.ground_j)
            scored.append((fitted * (1 - GEOMETRY.square_w * skew), fitted, draft))
        _score, fitted, draft = max(scored, key=lambda x: x[0])
        if it >= 1 and fitted >= scale - _SCALE_TOLERANCE:
            return fitted, draft
        scale = fitted if it < _DAMPING_FROM else fitted * _DAMPING_FACTOR
    raise CityLayoutError(CITY_TEXT.LAYOUT_FAILED)


def _validate(specs: tuple[CitySpec, ...]) -> None:
    ids = [s.id for s in specs]
    if len(set(ids)) != len(ids):
        raise ValueError("版位物件 id 重複")
    if sum(1 for s in specs if s.kind == SPEC_KIND_SITE) != 1:
        raise ValueError("版位物件必須恰有一個工地")


@functools.lru_cache(maxsize=8)
def layout_city(*, specs: tuple[CitySpec, ...], max_asset: float) -> CityLayout:
    """確定性排版；物件數（含工地）超過 compact_n 時名稱牌改為只放名稱。

    Args:
        specs: 版位物件，恰含一個 kind="site"，id 不重複。
        max_asset: 資產高度分母。

    Returns:
        frozen 的版位結果；相同輸入由 lru_cache 回傳同一物件。

    Raises:
        CityLayoutError: 迭代上限內無法收斂。
        ValueError: specs 沒有或有多個工地、id 重複。
    """
    _validate(specs)
    compact = len(specs) > GEOMETRY.compact_n
    objs = _build_objects(specs, max_asset, compact)
    fitted, draft = _solve(_group_by_zone(objs))

    lots: dict[str, Lot] = {}
    plates: dict[str, PlateSize] = {}
    names = {s.id: s.name for s in specs}
    for r, row in enumerate(draft.rows):
        for proto, j in row:
            obj = proto.obj
            lots[obj.id] = obj.lot(draft.row_i[r], j)
            plates[obj.id] = PlateSize(
                obj.plate_w, obj.plate_h, geometry.wrap_name(name=names[obj.id])
            )
    top = 0.0
    for obj in objs:
        for _kind, points in geometry.obstacles(
            kind=obj.kind, lot=lots[obj.id], height=obj.height, roof=obj.roof, scale=1.0
        ):
            top = max(top, max(-y for _x, y in points))
    order = [s.id for s in specs]
    return CityLayout(
        scale=fitted,
        ground_i=draft.ground_i,
        ground_j=draft.ground_j,
        top_pad=math.ceil(top + 4),
        lots=tuple((k, lots[k]) for k in order),
        plates=tuple((k, plates[k]) for k in order),
        roads=tuple(draft.roads),
        blocks=tuple(draft.blocks),
        compact=compact,
    )


# ---------------------------------------------------------------- 驗證
def _frame(layout: CityLayout, canvas_w: float) -> tuple[float, float, float, int]:
    """(scale, ox, oy, 畫布高)；ox/oy 是地盤頂點在畫布上的位置（city.js `resize`）。"""
    scale = geometry.fit_scale(
        ground_i=layout.ground_i, ground_j=layout.ground_j, canvas_w=canvas_w
    )
    ox = canvas_w / 2 - (layout.ground_i - layout.ground_j) * GEOMETRY.ux * scale / 2
    overlay = GEOMETRY.overlay_h if canvas_w < GEOMETRY.narrow_w else 0
    oy = GEOMETRY.top_m + overlay + layout.top_pad * scale
    height = math.ceil(
        oy
        + (layout.ground_i + layout.ground_j) * GEOMETRY.vy * scale
        + GEOMETRY.soil * scale
        + GEOMETRY.bot_m
    )
    return scale, ox, oy, height


def _scene(
    layout: CityLayout, specs: tuple[CitySpec, ...], max_asset: float, scale: float
) -> tuple[dict[str, Rect], list[tuple[str, str, list[Point]]]]:
    """名稱牌外框與障礙物（座標原點＝地盤頂點）。"""
    by_id = {s.id: s for s in specs}
    plate_sizes = dict(layout.plates)
    plates: dict[str, Rect] = {}
    obstacles: list[tuple[str, str, list[Point]]] = []
    for key, lot in layout.lots:
        spec = by_id[key]
        kind, height, roof = _geometry_kind(spec, max_asset)
        size = plate_sizes[key]
        plates[key] = geometry.plate_rect(
            kind=kind, lot=lot, width=size.width, height=size.height, scale=scale
        )
        for shape_kind, points in geometry.obstacles(
            kind=kind, lot=lot, height=height, roof=roof, scale=scale
        ):
            obstacles.append((key, shape_kind, points))
    return plates, obstacles


def _geometry_kind(spec: CitySpec, max_asset: float) -> tuple[str, float, float]:
    if spec.kind == SPEC_KIND_SITE:
        return CITY_ZONE.SITE, GEOMETRY.house_full, GEOMETRY.house_roof
    if spec.kind == SPEC_KIND_LIABILITY:
        return CITY_SHAPE.PIT, 0.0, 0.0
    roof = GEOMETRY.silo_roof if spec.shape == CITY_SHAPE.SILO else 0.0
    return _KIND_BUILDING, geometry.asset_height(value=spec.peak, max_asset=max_asset), roof


def _plate_outside_ground(plate: Rect, layout: CityLayout, scale: float) -> bool:
    for x, y in (
        (plate[0], plate[3]),
        (plate[2], plate[3]),
        (plate[0], plate[1]),
        (plate[2], plate[1]),
    ):
        u, v = x / (GEOMETRY.ux * scale), y / (GEOMETRY.vy * scale)
        i, j = (v + u) / 2, (v - u) / 2
        if not (-1e-6 <= i <= layout.ground_i + 1e-6 and -1e-6 <= j <= layout.ground_j + 1e-6):
            return True
    return False


def check(
    *,
    layout: CityLayout,
    specs: tuple[CitySpec, ...],
    max_asset: float,
    canvas_w: float = GEOMETRY.design_width,
) -> list[tuple[str, str]]:
    """列出所有衝突；空清單＝合格。供測試使用。

    涵蓋：名稱牌碰到建築／工地／吊車／坑洞／旗桿、名稱牌互疊、名稱牌出地盤、
    旗桿碰到建築、任何東西出畫布。

    Args:
        layout: 待檢查的版位。
        specs: 產生版位的物件。
        max_asset: 資產高度分母。
        canvas_w: 畫布寬度。

    Returns:
        (物件 id, 衝突種類) 清單。
    """
    scale, ox, oy, canvas_h = _frame(layout, canvas_w)
    plates, obstacles = _scene(layout, specs, max_asset, scale)
    out: list[tuple[str, str]] = []
    for key, rect in plates.items():
        if _plate_outside_ground(rect, layout, scale):
            out.append((key, "plate-outside-ground"))
        out += [
            (key, f"hit-{other}-{kind}")
            for other, kind, points in obstacles
            if _rect_hits_polygon(rect, points)
        ]
        out += [
            (key, f"overlap-{other}")
            for other, other_rect in plates.items()
            if key < other and _rects_hit(rect, other_rect)
        ]
    site_ids = {s.id for s in specs if s.kind == SPEC_KIND_SITE}
    for _key, kind, points in obstacles:
        if kind != "flags":
            continue
        box = _bbox(points)
        out += [
            ("flags", f"hit-{other}")
            for other, _kind, shape in obstacles
            if other not in site_ids and _rect_hits_polygon(box, shape)
        ]
    xs = [p[0] for _k, _kind, pts in obstacles for p in pts]
    ys = [p[1] for _k, _kind, pts in obstacles for p in pts]
    xs += [x for r in plates.values() for x in (r[0], r[2])]
    ys += [y for r in plates.values() for y in (r[1], r[3])]
    xs += [-layout.ground_j * GEOMETRY.ux * scale, layout.ground_i * GEOMETRY.ux * scale]
    ys += [(layout.ground_i + layout.ground_j) * GEOMETRY.vy * scale + GEOMETRY.soil * scale]
    if min(xs) + ox < 0 or max(xs) + ox > canvas_w or min(ys) + oy < 0 or max(ys) + oy > canvas_h:
        out.append(("frame", "outside-canvas"))
    return out
