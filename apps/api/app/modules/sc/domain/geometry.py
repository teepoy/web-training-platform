from __future__ import annotations


def compute_die_and_index(
    wafer_x: int,
    wafer_y: int,
    origin_x: int,
    origin_y: int,
    die_size_x: int,
    die_size_y: int,
) -> tuple[int, int, int, int]:
    """Compute die-local coordinates and die indices from wafer coordinates.

    Returns (die_x, die_y, index_x, index_y) where:
      - die_xy = (wafer_xy - origin_xy) % die_size_xy (die-local offset)
      - index_xy = (wafer_xy - origin_xy) // die_size_xy (die grid index)

    Args:
        wafer_x: Wafer X coordinate.
        wafer_y: Wafer Y coordinate.
        origin_x: Die grid origin X offset.
        origin_y: Die grid origin Y offset.
        die_size_x: Die width in X (clamped to minimum 1).
        die_size_y: Die height in Y (clamped to minimum 1).

    Returns:
        Tuple of (die_x, die_y, index_x, index_y).
    """
    guard_x = max(1, die_size_x)
    guard_y = max(1, die_size_y)

    offset_x = wafer_x - origin_x
    offset_y = wafer_y - origin_y

    die_x = offset_x % guard_x
    die_y = offset_y % guard_y
    index_x = offset_x // guard_x
    index_y = offset_y // guard_y

    return (die_x, die_y, index_x, index_y)
