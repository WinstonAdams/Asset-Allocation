"""城市版位純模組：分區街廓、名稱牌不衝突、確定性與快取、精簡旗標、無法收斂的錯誤路徑。"""

# ==== 原生（標準庫） ====
import dataclasses
import time
from concurrent.futures import ThreadPoolExecutor

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.city import layout as layout_module
from asset_lab.city.geometry import GEOMETRY
from asset_lab.city.layout import CityLayout, CitySpec, check, layout_city
from asset_lab.core.constants import CITY_SHAPE, CITY_ZONE
from asset_lab.core.exceptions import CityLayoutError

SITE_ID = "site"
MAX_ASSET = 5_000_000.0
KIND_ASSET = "asset"
KIND_LIABILITY = "liability"
KIND_SITE = "site"

# 虛構項目：(名稱, 分區, 峰值)；台股與美股同屬股票分區
SAMPLE_ASSETS = (
    ("活存甲", CITY_ZONE.CASH, 300_000.0),
    ("活存乙", CITY_ZONE.CASH, 120_000.0),
    ("定存甲", CITY_ZONE.DEPOSIT, 800_000.0),
    ("台股甲", CITY_ZONE.STOCK, 5_000_000.0),
    ("台股乙", CITY_ZONE.STOCK, 2_400_000.0),
    ("美股 Alpha Fund", CITY_ZONE.STOCK, 3_100_000.0),
    ("保單甲", CITY_ZONE.INSURANCE, 600_000.0),
    ("房貸示意", CITY_ZONE.DEBT, 2_000_000.0),
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    layout_city.cache_clear()
    yield
    layout_city.cache_clear()


def _sub(kind: str, peak: float) -> str:
    prefix = "應繳 " if kind == KIND_LIABILITY else ""
    return f"{prefix}{peak / 10000:,.1f} 萬"


def _spec(idx: int, name: str, zone: str, peak: float) -> CitySpec:
    kind = KIND_LIABILITY if zone == CITY_ZONE.DEBT else KIND_ASSET
    return CitySpec(
        id=f"h{idx}",
        name=name,
        zone=zone,
        kind=kind,
        shape=CITY_SHAPE.BY_ZONE[zone],
        peak=peak,
        sub_reference=_sub(kind, peak),
    )


def _site_spec() -> CitySpec:
    return CitySpec(
        id=SITE_ID,
        name="購屋工地",
        zone=CITY_ZONE.SITE,
        kind=KIND_SITE,
        shape="",
        peak=0.0,
        sub_reference="自備款 9,999.9 萬",
    )


def _sample_specs() -> tuple[CitySpec, ...]:
    items = [_spec(i, *row) for i, row in enumerate(SAMPLE_ASSETS)]
    return (*items, _site_spec())


def _many_specs(count: int) -> tuple[CitySpec, ...]:
    """count 個項目（不含工地），分區輪流、峰值遞減。"""
    zones = (
        CITY_ZONE.CASH,
        CITY_ZONE.DEPOSIT,
        CITY_ZONE.STOCK,
        CITY_ZONE.INSURANCE,
        CITY_ZONE.DEBT,
    )
    items = [
        _spec(i, f"項目 {i:02d}", zones[i % len(zones)], 4_000_000.0 - i * 90_000.0)
        for i in range(count)
    ]
    return (*items, _site_spec())


def _lots(layout: CityLayout) -> dict[str, tuple[int, int, int, int]]:
    return dict(layout.lots)


class TestZonesAndNoConflicts:
    @pytest.mark.scenario("SC-152")
    def test_sc152_items_sit_in_their_zone_block(self):
        specs = _sample_specs()
        layout = layout_city(specs=specs, max_asset=MAX_ASSET)
        lots = _lots(layout)
        for spec in specs:
            i, j, _w, _d = lots[spec.id]
            zone_blocks = [b for b in layout.blocks if b[0] == spec.zone]
            assert any(i0 <= i < i1 and j0 <= j < j1 for _z, i0, i1, j0, j1 in zone_blocks), spec.id

    @pytest.mark.scenario("SC-152")
    def test_sc152_tw_and_us_stock_share_one_block(self):
        specs = _sample_specs()
        layout = layout_city(specs=specs, max_asset=MAX_ASSET)
        stock_blocks = [b for b in layout.blocks if b[0] == CITY_ZONE.STOCK]
        assert len(stock_blocks) == 1
        _z, i0, i1, j0, j1 = stock_blocks[0]
        lots = _lots(layout)
        stock_ids = [s.id for s in specs if s.zone == CITY_ZONE.STOCK]
        assert len(stock_ids) == 3
        assert all(i0 <= lots[k][0] < i1 and j0 <= lots[k][1] < j1 for k in stock_ids)

    @pytest.mark.scenario("SC-152")
    def test_sc152_every_zone_and_site_have_exactly_one_block(self):
        layout = layout_city(specs=_sample_specs(), max_asset=MAX_ASSET)
        zones = [b[0] for b in layout.blocks]
        assert sorted(zones) == sorted(
            [
                CITY_ZONE.CASH,
                CITY_ZONE.DEPOSIT,
                CITY_ZONE.STOCK,
                CITY_ZONE.INSURANCE,
                CITY_ZONE.DEBT,
                CITY_ZONE.SITE,
            ]
        )

    @pytest.mark.scenario("SC-152")
    @pytest.mark.parametrize("canvas_w", [818.0, 1000.0, 1280.0, 1600.0])
    def test_sc152_no_conflicts_across_canvas_widths(self, canvas_w):
        specs = _sample_specs()
        layout = layout_city(specs=specs, max_asset=MAX_ASSET)
        assert check(layout=layout, specs=specs, max_asset=MAX_ASSET, canvas_w=canvas_w) == []

    @pytest.mark.scenario("SC-152")
    @pytest.mark.parametrize("count", [1, 5, 11, 12, 20, 30])
    def test_sc152_no_conflicts_for_various_item_counts(self, count):
        specs = _many_specs(count)
        layout = layout_city(specs=specs, max_asset=4_000_000.0)
        assert check(layout=layout, specs=specs, max_asset=4_000_000.0) == []

    @pytest.mark.scenario("SC-152")
    def test_sc152_lots_do_not_overlap_and_stay_in_ground(self):
        specs = _many_specs(20)
        layout = layout_city(specs=specs, max_asset=4_000_000.0)
        rects = list(layout.lots)
        for _k, (i, j, w, d) in rects:
            assert 0 <= i and i + w <= layout.ground_i
            assert 0 <= j and j + d <= layout.ground_j
        for a in range(len(rects)):
            for b in range(a + 1, len(rects)):
                (_ka, (ia, ja, wa, da)), (_kb, (ib, jb, wb, db)) = rects[a], rects[b]
                separate = ia + wa <= ib or ib + wb <= ia or ja + da <= jb or jb + db <= ja
                assert separate, (rects[a][0], rects[b][0])

    @pytest.mark.scenario("SC-152")
    def test_sc152_check_reports_conflict_when_lots_collide(self):
        specs = _sample_specs()
        layout = layout_city(specs=specs, max_asset=MAX_ASSET)
        lots = dict(layout.lots)
        first, second = specs[0].id, specs[1].id
        lots[second] = lots[first]
        broken = dataclasses.replace(layout, lots=tuple(lots.items()))
        assert check(layout=broken, specs=specs, max_asset=MAX_ASSET) != []

    @pytest.mark.scenario("SC-152")
    def test_sc152_check_reports_outside_canvas_when_scale_too_large(self):
        specs = _sample_specs()
        layout = layout_city(specs=specs, max_asset=MAX_ASSET)
        too_wide = dataclasses.replace(layout, ground_i=layout.ground_i + 40)
        assert check(layout=too_wide, specs=specs, max_asset=MAX_ASSET) != []

    @pytest.mark.scenario("SC-152")
    def test_sc152_site_only_layout_is_valid(self):
        specs = (_site_spec(),)
        layout = layout_city(specs=specs, max_asset=0.0)
        assert [k for k, _ in layout.lots] == [SITE_ID]
        assert check(layout=layout, specs=specs, max_asset=0.0) == []

    @pytest.mark.scenario("SC-152")
    def test_sc152_zero_peak_items_are_laid_out(self):
        items = [_spec(0, "全空項目", CITY_ZONE.CASH, 0.0), _site_spec()]
        specs = tuple(items)
        layout = layout_city(specs=specs, max_asset=0.0)
        assert check(layout=layout, specs=specs, max_asset=0.0) == []

    @pytest.mark.scenario("SC-152")
    def test_sc152_long_name_is_wrapped_into_plate_lines(self):
        long_name = "非常長的名稱示範項目 Super Long Fund Name"
        specs = (_spec(0, long_name, CITY_ZONE.STOCK, 1_000_000.0), _site_spec())
        layout = layout_city(specs=specs, max_asset=1_000_000.0)
        plate = dict(layout.plates)["h0"]
        assert 1 <= len(plate.lines) <= 2
        assert plate.width > 0 and plate.height > 0
        assert check(layout=layout, specs=specs, max_asset=1_000_000.0) == []


class TestDeterminismAndCache:
    @pytest.mark.scenario("SC-153")
    def test_sc153_repeated_layout_is_identical(self):
        specs = _many_specs(18)
        first = layout_city(specs=specs, max_asset=4_000_000.0)
        layout_city.cache_clear()
        second = layout_city(specs=specs, max_asset=4_000_000.0)
        assert first == second
        assert first is not second

    @pytest.mark.scenario("SC-153")
    def test_sc153_positions_do_not_move_between_months(self):
        specs = _sample_specs()
        month_a = layout_city(specs=specs, max_asset=MAX_ASSET)
        month_b = layout_city(specs=tuple(specs), max_asset=MAX_ASSET)
        assert month_a is month_b
        assert layout_city.cache_info().hits >= 1

    @pytest.mark.scenario("SC-153")
    def test_sc153_different_inputs_do_not_share_results(self):
        small = layout_city(specs=_many_specs(5), max_asset=4_000_000.0)
        large = layout_city(specs=_many_specs(25), max_asset=4_000_000.0)
        assert len(small.lots) == 6
        assert len(large.lots) == 26

    @pytest.mark.scenario("SC-153")
    def test_sc153_thirty_buildings_cold_start_within_50ms(self):
        specs = _many_specs(30)
        assert len(specs) == 31  # 30 棟項目＋購屋工地
        best = float("inf")
        for _ in range(7):
            layout_city.cache_clear()
            start = time.perf_counter()
            layout_city(specs=specs, max_asset=4_000_000.0)
            best = min(best, time.perf_counter() - start)
        assert best < 0.05

    @pytest.mark.scenario("SC-153")
    def test_sc153_concurrent_sessions_do_not_affect_each_other(self):
        inputs = [(_many_specs(n), 4_000_000.0) for n in (6, 12, 18, 24)] * 4
        expected = []
        for specs, peak in inputs:
            layout_city.cache_clear()
            expected.append(layout_city(specs=specs, max_asset=peak))
        layout_city.cache_clear()

        def run(args):
            return layout_city(specs=args[0], max_asset=args[1])

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, inputs))
        assert results == expected


class TestCompactFlag:
    @pytest.mark.scenario("SC-154")
    def test_sc154_not_compact_at_threshold(self):
        specs = _many_specs(GEOMETRY.compact_n - 1)
        assert len(specs) == GEOMETRY.compact_n
        assert layout_city(specs=specs, max_asset=4_000_000.0).compact is False

    @pytest.mark.scenario("SC-154")
    def test_sc154_compact_above_threshold(self):
        specs = _many_specs(GEOMETRY.compact_n)
        assert len(specs) == GEOMETRY.compact_n + 1
        assert layout_city(specs=specs, max_asset=4_000_000.0).compact is True

    @pytest.mark.scenario("SC-154")
    def test_sc154_compact_plates_drop_the_amount_line(self):
        full = layout_city(specs=_many_specs(3), max_asset=4_000_000.0)
        compact = layout_city(specs=_many_specs(GEOMETRY.compact_n), max_asset=4_000_000.0)
        full_h = dict(full.plates)["h0"].height
        compact_h = dict(compact.plates)["h0"].height
        assert compact_h < full_h
        assert compact_h == int(GEOMETRY.name_px + 2 * GEOMETRY.pad_y)

    @pytest.mark.scenario("SC-154")
    def test_sc154_compact_layout_has_no_conflicts(self):
        specs = _many_specs(GEOMETRY.compact_n + 6)
        layout = layout_city(specs=specs, max_asset=4_000_000.0)
        assert check(layout=layout, specs=specs, max_asset=4_000_000.0) == []


class TestLayoutError:
    @pytest.mark.scenario("SC-163")
    def test_sc163_non_convergence_raises_city_layout_error(self, monkeypatch):
        monkeypatch.setattr(layout_module, "_MAX_ITERATIONS", 1)
        with pytest.raises(CityLayoutError):
            layout_city(specs=_sample_specs(), max_asset=MAX_ASSET)

    @pytest.mark.scenario("SC-163")
    def test_sc163_failure_is_not_cached(self, monkeypatch):
        specs = _sample_specs()
        with monkeypatch.context() as patch:
            patch.setattr(layout_module, "_MAX_ITERATIONS", 1)
            with pytest.raises(CityLayoutError):
                layout_city(specs=specs, max_asset=MAX_ASSET)
        assert len(layout_city(specs=specs, max_asset=MAX_ASSET).lots) == len(specs)

    @pytest.mark.scenario("SC-163")
    def test_sc163_specs_without_site_are_rejected(self):
        items = tuple(_spec(i, *row) for i, row in enumerate(SAMPLE_ASSETS))
        with pytest.raises(ValueError):
            layout_city(specs=items, max_asset=MAX_ASSET)

    @pytest.mark.scenario("SC-163")
    def test_sc163_multiple_sites_are_rejected(self):
        other = dataclasses.replace(_site_spec(), id="site2")
        with pytest.raises(ValueError):
            layout_city(specs=(*_sample_specs(), other), max_asset=MAX_ASSET)

    @pytest.mark.scenario("SC-163")
    def test_sc163_duplicate_ids_are_rejected(self):
        first = _spec(0, "活存甲", CITY_ZONE.CASH, 100_000.0)
        with pytest.raises(ValueError):
            layout_city(specs=(first, first, _site_spec()), max_asset=MAX_ASSET)
