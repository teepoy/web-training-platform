from __future__ import annotations

from app.modules.sc.app.services.shuffle import SC_IMPORT_SHUFFLE_SEED, get_shuffled_ids


def test_shuffle_reproducible() -> None:
    ids = list(range(100))
    a = get_shuffled_ids(ids, seed=99)
    b = get_shuffled_ids(ids, seed=99)
    assert a == b


def test_shuffle_different_seed() -> None:
    ids = list(range(100))
    a = get_shuffled_ids(ids, seed=1)
    b = get_shuffled_ids(ids, seed=2)
    assert a != b


def test_shuffle_all_present() -> None:
    ids = [10, 20, 30, 40, 50]
    result = get_shuffled_ids(ids, seed=SC_IMPORT_SHUFFLE_SEED)
    assert sorted(result) == sorted(ids)


def test_shuffle_empty() -> None:
    assert get_shuffled_ids([], seed=0) == []
