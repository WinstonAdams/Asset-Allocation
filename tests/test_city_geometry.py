"""城市幾何純模組：高度、坑洞深度，以及與 city.js 共用的投影／名稱牌／障礙物公式。"""

# ==== 原生（標準庫） ====
import json
import math

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.city import geometry
from asset_lab.city.geometry import GEOMETRY

SC_LOT = (3, 4, 2, 2)


class TestAssetHeight:
    @pytest.mark.scenario("SC-137")
    def test_sc137_height_follows_sqrt_ratio(self):
        max_asset = 4_000_000
        h_a = geometry.asset_height(value=1_000_000, max_asset=max_asset)
        h_b = geometry.asset_height(value=250_000, max_asset=max_asset)
        assert h_a == pytest.approx(GEOMETRY.h_top * 0.5)
        assert h_b == pytest.approx(GEOMETRY.h_top * 0.25)

    @pytest.mark.scenario("SC-137")
    def test_sc137_peak_reaches_top(self):
        assert geometry.asset_height(value=4_000_000, max_asset=4_000_000) == pytest.approx(
            GEOMETRY.h_top
        )

    @pytest.mark.scenario("SC-137")
    def test_sc137_same_denominator_makes_months_comparable(self):
        low = geometry.asset_height(value=100, max_asset=400)
        high = geometry.asset_height(value=200, max_asset=400)
        assert low < high

    @pytest.mark.scenario("SC-137")
    def test_sc137_small_value_clamped_to_minimum(self):
        assert geometry.asset_height(value=1, max_asset=4_000_000) == GEOMETRY.h_min

    @pytest.mark.scenario("SC-137")
    def test_sc137_floor_boundary_is_continuous(self):
        # 剛好落在下限的比例：比它大一點高於下限，等於或小於回下限
        ratio = (GEOMETRY.h_min / GEOMETRY.h_top) ** 2
        at_floor = geometry.asset_height(value=ratio * 1000, max_asset=1000)
        above = geometry.asset_height(value=ratio * 1000 * 1.1, max_asset=1000)
        below = geometry.asset_height(value=ratio * 1000 * 0.9, max_asset=1000)
        assert at_floor == pytest.approx(GEOMETRY.h_min)
        assert above > GEOMETRY.h_min
        assert below == GEOMETRY.h_min

    @pytest.mark.scenario("SC-137")
    @pytest.mark.parametrize("max_asset", [0, -5])
    def test_sc137_non_positive_denominator_draws_minimum(self, max_asset):
        assert geometry.asset_height(value=500, max_asset=max_asset) == GEOMETRY.h_min

    @pytest.mark.scenario("SC-137")
    @pytest.mark.parametrize("value", [0, -100])
    def test_sc137_zero_or_negative_value_draws_minimum(self, value):
        assert geometry.asset_height(value=value, max_asset=1000) == GEOMETRY.h_min


class TestPitDepth:
    @pytest.mark.scenario("SC-138")
    def test_sc138_depth_scales_against_liability_peak(self):
        depth = geometry.pit_depth(value=6_000_000, max_liability=8_000_000)
        peak = geometry.pit_depth(value=8_000_000, max_liability=8_000_000)
        assert GEOMETRY.pit_min_depth < depth < peak
        assert peak == pytest.approx(GEOMETRY.pit_max_depth)

    @pytest.mark.scenario("SC-138")
    def test_sc138_denominator_is_liability_own_peak(self):
        # 同樣 600 萬，分母不同深度就不同：證明深度只看自己傳入的負債最高值
        shallow = geometry.pit_depth(value=6_000_000, max_liability=24_000_000)
        deep = geometry.pit_depth(value=6_000_000, max_liability=8_000_000)
        assert shallow < deep

    @pytest.mark.scenario("SC-138")
    @pytest.mark.parametrize("max_liability", [0, -1])
    def test_sc138_no_liability_peak_draws_shallowest(self, max_liability):
        depth = geometry.pit_depth(value=100, max_liability=max_liability)
        assert depth == GEOMETRY.pit_min_depth

    @pytest.mark.scenario("SC-138")
    def test_sc138_zero_value_draws_shallowest(self):
        assert geometry.pit_depth(value=0, max_liability=800) == GEOMETRY.pit_min_depth

    @pytest.mark.scenario("SC-138")
    def test_sc138_small_liability_clamped_to_shallowest(self):
        assert geometry.pit_depth(value=1, max_liability=800_000_000) == GEOMETRY.pit_min_depth


class TestGeometryConstants:
    @pytest.mark.scenario("SC-152")
    def test_geometry_json_round_trips_every_field(self):
        decoded = json.loads(geometry.geometry_json())
        assert set(decoded) == {f for f in GEOMETRY.__dataclass_fields__}
        assert decoded["h_top"] == GEOMETRY.h_top
        assert decoded["row_choices"] == list(GEOMETRY.row_choices)

    @pytest.mark.scenario("SC-152")
    def test_geometry_is_immutable(self):
        with pytest.raises(AttributeError):
            GEOMETRY.h_top = 1.0  # type: ignore[misc]

    @pytest.mark.scenario("SC-138")
    def test_pit_depth_constants_are_ordered(self):
        assert 0 < GEOMETRY.pit_min_depth < GEOMETRY.pit_max_depth

    @pytest.mark.scenario("SC-152")
    def test_site_reference_amount_covers_widest_plate_text(self):
        assert GEOMETRY.site_reference_amount >= 10_000_000


class TestProjection:
    @pytest.mark.scenario("SC-152")
    def test_origin_projects_to_origin(self):
        assert geometry.project(i=0, j=0, scale=1.0) == (0.0, 0.0)

    @pytest.mark.scenario("SC-152")
    def test_projection_is_isometric(self):
        x, y = geometry.project(i=3, j=1, scale=2.0)
        assert x == pytest.approx((3 - 1) * GEOMETRY.ux * 2.0)
        assert y == pytest.approx((3 + 1) * GEOMETRY.vy * 2.0)

    @pytest.mark.scenario("SC-152")
    def test_swapping_axes_mirrors_x(self):
        a = geometry.project(i=5, j=2, scale=1.0)
        b = geometry.project(i=2, j=5, scale=1.0)
        assert a[0] == -b[0]
        assert a[1] == b[1]


class TestFitScale:
    @pytest.mark.scenario("SC-152")
    def test_ground_fits_inside_canvas_width(self):
        sc = geometry.fit_scale(ground_i=20, ground_j=20, canvas_w=GEOMETRY.design_width)
        used = 40 * GEOMETRY.ux * sc + 2 * GEOMETRY.side_m
        assert used <= GEOMETRY.design_width + 1e-9

    @pytest.mark.scenario("SC-152")
    def test_scale_is_capped_for_small_ground(self):
        sc = geometry.fit_scale(ground_i=1, ground_j=1, canvas_w=2000)
        assert sc == GEOMETRY.sc_max

    @pytest.mark.scenario("SC-152")
    def test_narrower_canvas_gives_smaller_scale(self):
        wide = geometry.fit_scale(ground_i=20, ground_j=20, canvas_w=900)
        narrow = geometry.fit_scale(ground_i=20, ground_j=20, canvas_w=400)
        assert narrow < wide


class TestTextAndPlate:
    @pytest.mark.scenario("SC-152")
    def test_text_width_by_character_class(self):
        assert geometry.text_width(text="中", px=10) == pytest.approx(10.0)
        assert geometry.text_width(text="1", px=10) == pytest.approx(6.0)
        assert geometry.text_width(text="A", px=10) == pytest.approx(7.2)
        assert geometry.text_width(text=" ", px=10) == pytest.approx(3.0)
        assert geometry.text_width(text="a", px=10) == pytest.approx(6.0)

    @pytest.mark.scenario("SC-152")
    def test_text_width_empty_string_is_zero(self):
        assert geometry.text_width(text="", px=11) == 0

    @pytest.mark.scenario("SC-152")
    def test_short_name_stays_one_line(self):
        assert geometry.wrap_name(name="活存") == ("活存",)

    @pytest.mark.scenario("SC-152")
    def test_long_name_wraps_at_space(self):
        lines = geometry.wrap_name(name="Total World Index")
        assert lines == ("Total World", "Index")

    @pytest.mark.scenario("SC-152")
    def test_long_name_without_space_hard_cuts(self):
        lines = geometry.wrap_name(name="很長很長很長很長很長很長很長很長")
        assert len(lines) == 2
        assert "".join(lines) == "很長很長很長很長很長很長很長很長"

    @pytest.mark.scenario("SC-152")
    def test_very_long_name_truncates_second_line_with_ellipsis(self):
        lines = geometry.wrap_name(name="極長" * 20)
        assert len(lines) == 2
        assert lines[1].endswith("…")
        for line in lines:
            width = geometry.text_width(text=line, px=GEOMETRY.name_px)
            assert width <= GEOMETRY.name_max_w

    @pytest.mark.scenario("SC-152")
    def test_empty_name_gives_single_empty_line(self):
        assert geometry.wrap_name(name="") == ("",)

    @pytest.mark.scenario("SC-154")
    def test_plate_size_compact_has_name_only(self):
        w, h = geometry.plate_size(lines=("活存",), sub=None)
        expected_h = GEOMETRY.name_px + 2 * GEOMETRY.pad_y
        assert h == expected_h
        assert w == math.ceil(
            geometry.text_width(text="活存", px=GEOMETRY.name_px) + GEOMETRY.pad_l + GEOMETRY.pad_r
        )

    @pytest.mark.scenario("SC-152")
    def test_plate_size_with_sub_is_taller_and_wide_enough(self):
        compact = geometry.plate_size(lines=("活存",), sub=None)
        full = geometry.plate_size(lines=("活存",), sub="1,234.5 萬")
        assert full[1] == compact[1] + GEOMETRY.sub_px + GEOMETRY.line_gap
        sub_w = geometry.text_width(text="1,234.5 萬", px=GEOMETRY.sub_px)
        assert full[0] >= sub_w + GEOMETRY.pad_l + GEOMETRY.pad_r

    @pytest.mark.scenario("SC-152")
    def test_plate_size_two_lines_adds_line_gap(self):
        one = geometry.plate_size(lines=("甲",), sub=None)
        two = geometry.plate_size(lines=("甲", "乙"), sub=None)
        assert two[1] == one[1] + GEOMETRY.name_px + GEOMETRY.line_gap


class TestPlateAndObstacles:
    @pytest.mark.scenario("SC-152")
    def test_plate_is_centered_below_asset_footprint(self):
        rect = geometry.plate_rect(kind="asset", lot=SC_LOT, width=60, height=20, scale=1.0)
        i, j, w, d = SC_LOT
        cx, _ = geometry.project(i=i + w / 2, j=j + d / 2, scale=1.0)
        assert (rect[0] + rect[2]) / 2 == pytest.approx(cx)
        assert rect[2] - rect[0] == 60
        assert rect[3] - rect[1] == 20
        front_y = geometry.project(i=i + w - GEOMETRY.pad, j=j + d - GEOMETRY.pad, scale=1.0)[1]
        assert rect[1] == pytest.approx(front_y + GEOMETRY.lab_gap)

    @pytest.mark.scenario("SC-152")
    def test_pit_plate_uses_pit_padding(self):
        asset = geometry.plate_rect(kind="asset", lot=SC_LOT, width=60, height=20, scale=1.0)
        pit = geometry.plate_rect(kind="pit", lot=SC_LOT, width=60, height=20, scale=1.0)
        assert pit[1] > asset[1]

    @pytest.mark.scenario("SC-152")
    def test_site_plate_sits_below_flag_row(self):
        flags = geometry.flag_rect(lot=SC_LOT, scale=1.0)
        plate = geometry.plate_rect(kind="house", lot=SC_LOT, width=80, height=20, scale=1.0)
        assert plate[1] == pytest.approx(flags[3] + 2)

    @pytest.mark.scenario("SC-152")
    def test_flag_rect_is_a_proper_rectangle_in_front_of_site(self):
        x0, y0, x1, y1 = geometry.flag_rect(lot=SC_LOT, scale=1.0)
        assert x0 < x1
        assert y0 < y1
        i, j, w, d = SC_LOT
        front_y = geometry.project(i=i + w, j=j + d, scale=1.0)[1]
        assert y1 > front_y

    @pytest.mark.scenario("SC-152")
    def test_flag_rect_scales_with_canvas_scale(self):
        small = geometry.flag_rect(lot=SC_LOT, scale=0.5)
        large = geometry.flag_rect(lot=SC_LOT, scale=1.0)
        assert (large[3] - large[1]) > (small[3] - small[1])

    @pytest.mark.scenario("SC-152")
    def test_asset_obstacle_is_building_hexagon_without_roof(self):
        shapes = geometry.obstacles(kind="asset", lot=SC_LOT, height=50, roof=0, scale=1.0)
        assert [name for name, _ in shapes] == ["building"]
        assert len(shapes[0][1]) == 6

    @pytest.mark.scenario("SC-152")
    def test_asset_obstacle_with_roof_adds_apex_above_footprint_center(self):
        roofed = geometry.obstacles(kind="asset", lot=SC_LOT, height=50, roof=18, scale=1.0)[0][1]
        assert len(roofed) == 7
        i, j, w, d = SC_LOT
        cx, cy = geometry.project(i=i + w / 2, j=j + d / 2, scale=1.0)
        assert roofed[-1] == pytest.approx((cx, cy - 50 - 18))

    @pytest.mark.scenario("SC-152")
    def test_taller_building_reaches_higher_on_screen(self):
        low = geometry.obstacles(kind="asset", lot=SC_LOT, height=20, roof=0, scale=1.0)[0][1]
        high = geometry.obstacles(kind="asset", lot=SC_LOT, height=80, roof=0, scale=1.0)[0][1]
        assert min(y for _, y in high) < min(y for _, y in low)

    @pytest.mark.scenario("SC-152")
    def test_pit_obstacle_is_flat_ground_quad(self):
        shapes = geometry.obstacles(kind="pit", lot=SC_LOT, height=0, roof=0, scale=1.0)
        assert [name for name, _ in shapes] == ["pit"]
        assert len(shapes[0][1]) == 4

    @pytest.mark.scenario("SC-152")
    def test_site_obstacles_cover_house_crane_and_flags(self):
        shapes = geometry.obstacles(kind="house", lot=SC_LOT, height=0, roof=0, scale=1.0)
        assert [name for name, _ in shapes] == ["house", "crane", "crane", "flags"]
        flags = next(poly for name, poly in shapes if name == "flags")
        x0, y0, x1, y1 = geometry.flag_rect(lot=SC_LOT, scale=1.0)
        assert flags == [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    @pytest.mark.scenario("SC-152")
    def test_obstacles_scale_linearly_for_ground_points(self):
        a = geometry.obstacles(kind="pit", lot=SC_LOT, height=0, roof=0, scale=1.0)[0][1]
        b = geometry.obstacles(kind="pit", lot=SC_LOT, height=0, roof=0, scale=2.0)[0][1]
        for (ax, ay), (bx, by) in zip(a, b, strict=True):
            assert bx == pytest.approx(ax * 2)
            assert by == pytest.approx(ay * 2)
