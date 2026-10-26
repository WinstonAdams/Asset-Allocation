"""ReadCache 單元測試：依 SQL 鍵存取、整批過期、世代擋住競態寫回（假時鐘，不依賴 Streamlit）。"""

# ==== 原生（標準庫） ====
import threading

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.repositories.read_cache import ReadCache

_KEY_A = ("SELECT 1 FROM t WHERE m = ?", ("2026-09",))
_KEY_B = ("SELECT 1 FROM t WHERE m = ?", ("2026-10",))


class _FakeClock:
    """可手動撥動的假時鐘。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> _FakeClock:
    return _FakeClock()


@pytest.fixture
def cache(clock: _FakeClock) -> ReadCache:
    return ReadCache(ttl_seconds=300, clock=clock)


@pytest.mark.scenario("SC-112")
def test_sc112_get_returns_none_when_missing(cache: ReadCache) -> None:
    assert cache.get(_KEY_A) is None


@pytest.mark.scenario("SC-112")
def test_sc112_put_then_get_returns_same_rows(cache: ReadCache) -> None:
    rows = [(1, "a"), (2, "b")]

    assert cache.put(_KEY_A, rows, generation=cache.generation()) is True

    assert cache.get(_KEY_A) == rows


@pytest.mark.scenario("SC-112")
def test_sc112_empty_rows_is_a_valid_hit(cache: ReadCache) -> None:
    cache.put(_KEY_A, [], generation=cache.generation())

    assert cache.get(_KEY_A) == []


@pytest.mark.scenario("SC-112")
def test_sc112_different_keys_are_independent(cache: ReadCache) -> None:
    cache.put(_KEY_A, [(1,)], generation=cache.generation())

    assert cache.get(_KEY_B) is None


@pytest.mark.scenario("SC-119")
def test_sc119_mutating_original_rows_after_put_does_not_change_cache(cache: ReadCache) -> None:
    rows = [(1,), (2,)]
    cache.put(_KEY_A, rows, generation=cache.generation())

    rows.append((3,))

    assert cache.get(_KEY_A) == [(1,), (2,)]


@pytest.mark.scenario("SC-113")
def test_sc113_clear_removes_all_entries(cache: ReadCache) -> None:
    cache.put(_KEY_A, [(1,)], generation=cache.generation())
    cache.put(_KEY_B, [(2,)], generation=cache.generation())

    cache.clear()

    assert cache.get(_KEY_A) is None
    assert cache.get(_KEY_B) is None


@pytest.mark.scenario("SC-113")
def test_sc113_clear_advances_generation(cache: ReadCache) -> None:
    before = cache.generation()

    cache.clear()

    assert cache.generation() == before + 1


@pytest.mark.scenario("SC-114")
def test_sc114_put_with_stale_generation_is_rejected(cache: ReadCache) -> None:
    # 查詢發出時取世代、回來前被 commit 清除：結果不得寫回
    generation = cache.generation()
    cache.clear()

    assert cache.put(_KEY_A, [(1,)], generation=generation) is False

    assert cache.get(_KEY_A) is None


@pytest.mark.scenario("SC-114")
def test_sc114_fence_keeps_entries_but_rejects_in_flight_put(cache: ReadCache) -> None:
    cache.put(_KEY_A, [(1,)], generation=cache.generation())
    in_flight = cache.generation()

    cache.fence()

    assert cache.get(_KEY_A) == [(1,)]
    assert cache.put(_KEY_B, [(2,)], generation=in_flight) is False
    assert cache.get(_KEY_B) is None


@pytest.mark.scenario("SC-115")
def test_sc115_expire_if_stale_is_noop_before_ttl(cache: ReadCache, clock: _FakeClock) -> None:
    cache.put(_KEY_A, [(1,)], generation=cache.generation())

    clock.now += 299

    assert cache.expire_if_stale() is False
    assert cache.get(_KEY_A) == [(1,)]


@pytest.mark.scenario("SC-115")
def test_sc115_expire_if_stale_clears_everything_at_ttl(
    cache: ReadCache, clock: _FakeClock
) -> None:
    cache.put(_KEY_A, [(1,)], generation=cache.generation())
    clock.now += 100
    cache.put(_KEY_B, [(2,)], generation=cache.generation())

    clock.now += 200  # 距第一筆寫入剛好 300 秒：整批過期，不是逐筆

    assert cache.expire_if_stale() is True
    assert cache.get(_KEY_A) is None
    assert cache.get(_KEY_B) is None


@pytest.mark.scenario("SC-115")
def test_sc115_ttl_starts_at_first_put_after_clear(cache: ReadCache, clock: _FakeClock) -> None:
    cache.put(_KEY_A, [(1,)], generation=cache.generation())
    clock.now += 250
    cache.clear()
    clock.now += 250  # 清除後沒有任何項目，不計時
    assert cache.expire_if_stale() is False

    cache.put(_KEY_B, [(2,)], generation=cache.generation())
    clock.now += 299

    assert cache.expire_if_stale() is False


@pytest.mark.scenario("SC-115")
def test_sc115_empty_cache_never_expires(cache: ReadCache, clock: _FakeClock) -> None:
    clock.now += 10_000

    assert cache.expire_if_stale() is False


@pytest.mark.scenario("SC-114")
def test_sc114_concurrent_put_and_clear_stay_consistent(cache: ReadCache) -> None:
    # 多執行緒同時寫入與清除不應拋例外
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for step in range(200):
                key = ("SELECT ?", (index, step))
                cache.put(key, [(step,)], generation=cache.generation())
                cache.get(key)
                if step % 50 == 0:
                    cache.clear()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
