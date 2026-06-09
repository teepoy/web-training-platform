from __future__ import annotations

import numpy as np

SC_IMPORT_SHUFFLE_SEED: int = 42


def get_shuffled_ids(all_ids: list[int], seed: int | None = None) -> list[int]:
    rng = np.random.default_rng(seed if seed is not None else SC_IMPORT_SHUFFLE_SEED)
    return rng.permutation(np.array(all_ids, dtype=np.int64)).tolist()
