from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from sampling_rules.errors import InvalidSamplingRuleError, MissingFieldError

RowT = TypeVar("RowT", bound=Mapping[str, object])

DYNAMIC_ADDER_FIELD = "dynamic_adder"
DYNAMIC_ADDER_DISTANCE_FIELD = "dynamic_adder_distance"
DYNAMIC_ADDER_REFERENCE_INDEX_FIELD = "dynamic_adder_reference_index"
DYNAMIC_CLUSTER_FIELD = "dynamic_cluster"
DYNAMIC_CLUSTER_ID_FIELD = "dynamic_cluster_id"
DYNAMIC_CLUSTER_NEIGHBOR_COUNT_FIELD = "dynamic_cluster_neighbor_count"
DYNAMIC_CLUSTER_ROLE_FIELD = "dynamic_cluster_role"


class AdderMatchMode(StrEnum):
    """How a previous-layer defect may suppress current-layer adders."""

    ANY_REFERENCE = "any_reference"
    ONE_TO_ONE = "one_to_one"


class ClusterPointRole(StrEnum):
    CORE = "core"
    BORDER = "border"
    NOISE = "noise"


@dataclass(frozen=True, slots=True)
class DynamicAdderConfig:
    """Configuration for current-to-reference layer coordinate matching.

    ``radius`` uses the same physical unit as the configured coordinate fields.
    The SC wafer coordinate contract uses nanometers, so 50 micrometers is
    represented as ``50_000``.
    """

    x_field: str
    y_field: str
    radius: float
    match_mode: AdderMatchMode


@dataclass(frozen=True, slots=True)
class DynamicClusterConfig:
    """DBSCAN configuration for the defects on the current map.

    ``minimum_points`` includes the defect itself, matching standard DBSCAN
    terminology. ``radius`` uses the same unit as the coordinate fields.
    """

    x_field: str
    y_field: str
    radius: float
    minimum_points: int


@dataclass(frozen=True, slots=True)
class DynamicAdderResult:
    adder: int
    matched_reference_index: int | None
    distance: float | None


@dataclass(frozen=True, slots=True)
class DynamicClusterResult:
    cluster_id: int
    role: ClusterPointRole
    neighbor_count: int

    @property
    def is_clustered(self) -> bool:
        return self.cluster_id > 0


def _read_coordinate(row: Mapping[str, object], path: str) -> float:
    current: object = row
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise MissingFieldError(f"spatial coordinate field {path!r} is missing")
        current = current[part]
    if isinstance(current, bool) or not isinstance(current, int | float):
        raise MissingFieldError(
            f"spatial coordinate field {path!r} must resolve to a finite number"
        )
    coordinate = float(current)
    if not math.isfinite(coordinate):
        raise MissingFieldError(
            f"spatial coordinate field {path!r} must resolve to a finite number"
        )
    return coordinate


def _coordinates(
    rows: Sequence[Mapping[str, object]],
    *,
    x_field: str,
    y_field: str,
) -> tuple[tuple[float, float], ...]:
    if not x_field.strip() or not y_field.strip():
        raise InvalidSamplingRuleError(
            "dynamic spatial calculations require non-empty x and y fields"
        )
    return tuple(
        (_read_coordinate(row, x_field), _read_coordinate(row, y_field)) for row in rows
    )


def _validate_radius(radius: float) -> float:
    if isinstance(radius, bool) or not isinstance(radius, int | float):
        raise InvalidSamplingRuleError("dynamic spatial radius must be a number")
    value = float(radius)
    if not math.isfinite(value) or value <= 0:
        raise InvalidSamplingRuleError(
            "dynamic spatial radius must be a finite positive number"
        )
    return value


class _SpatialIndex:
    def __init__(self, points: Sequence[tuple[float, float]], radius: float) -> None:
        self._points = points
        self._cell_size = radius
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, point in enumerate(points):
            self._cells[self._cell(point)].append(index)

    def _cell(self, point: tuple[float, float]) -> tuple[int, int]:
        return (
            math.floor(point[0] / self._cell_size),
            math.floor(point[1] / self._cell_size),
        )

    def within_radius(
        self,
        point: tuple[float, float],
        radius_squared: float,
        *,
        available: set[int] | None = None,
    ) -> list[tuple[float, int]]:
        cell_x, cell_y = self._cell(point)
        matches: list[tuple[float, int]] = []
        for offset_x in (-1, 0, 1):
            for offset_y in (-1, 0, 1):
                for index in self._cells.get(
                    (cell_x + offset_x, cell_y + offset_y), ()
                ):
                    if available is not None and index not in available:
                        continue
                    candidate = self._points[index]
                    distance_squared = (point[0] - candidate[0]) ** 2 + (
                        point[1] - candidate[1]
                    ) ** 2
                    if distance_squared <= radius_squared:
                        matches.append((distance_squared, index))
        matches.sort()
        return matches


def compute_dynamic_adders(
    current_rows: Sequence[RowT],
    reference_rows: Sequence[Mapping[str, object]],
    *,
    config: DynamicAdderConfig,
) -> tuple[DynamicAdderResult, ...]:
    """Classify current defects as adders by matching a user-selected layer.

    A current defect is an adder (``1``) when no eligible reference defect is
    within the inclusive radius. ``ONE_TO_ONE`` follows the conventional level
    comparison filter: once a previous-layer defect matches a current defect,
    it cannot suppress another current defect. Current input order is therefore
    significant in that mode. ``ANY_REFERENCE`` performs independent matching.
    """

    radius = _validate_radius(config.radius)
    if not isinstance(config.match_mode, AdderMatchMode):
        raise InvalidSamplingRuleError(
            "dynamic adder match_mode must be any_reference or one_to_one"
        )
    current_points = _coordinates(
        current_rows,
        x_field=config.x_field,
        y_field=config.y_field,
    )
    reference_points = _coordinates(
        reference_rows,
        x_field=config.x_field,
        y_field=config.y_field,
    )
    index = _SpatialIndex(reference_points, radius)
    available = (
        set(range(len(reference_points)))
        if config.match_mode is AdderMatchMode.ONE_TO_ONE
        else None
    )
    radius_squared = radius * radius
    results: list[DynamicAdderResult] = []
    for point in current_points:
        matches = index.within_radius(
            point,
            radius_squared,
            available=available,
        )
        if not matches:
            results.append(
                DynamicAdderResult(
                    adder=1,
                    matched_reference_index=None,
                    distance=None,
                )
            )
            continue
        distance_squared, reference_index = matches[0]
        if available is not None:
            available.remove(reference_index)
        results.append(
            DynamicAdderResult(
                adder=0,
                matched_reference_index=reference_index,
                distance=math.sqrt(distance_squared),
            )
        )
    return tuple(results)


def compute_dynamic_clusters(
    rows: Sequence[RowT],
    *,
    config: DynamicClusterConfig,
) -> tuple[DynamicClusterResult, ...]:
    """Run deterministic DBSCAN over current-map defect coordinates.

    Cluster IDs are one-based in first-core-point discovery order. Noise uses
    cluster ID ``0``. A point on the inclusive radius boundary is a neighbor.
    """

    radius = _validate_radius(config.radius)
    if (
        isinstance(config.minimum_points, bool)
        or not isinstance(config.minimum_points, int)
        or config.minimum_points < 2
    ):
        raise InvalidSamplingRuleError(
            "dynamic cluster minimum_points must be an integer of at least two"
        )
    points = _coordinates(rows, x_field=config.x_field, y_field=config.y_field)
    spatial_index = _SpatialIndex(points, radius)
    radius_squared = radius * radius
    labels = [-1] * len(points)
    roles = [ClusterPointRole.NOISE] * len(points)
    neighbor_counts = [0] * len(points)
    visited = [False] * len(points)
    cluster_id = 0

    def neighbors(point_index: int) -> list[int]:
        matches = spatial_index.within_radius(
            points[point_index],
            radius_squared,
        )
        neighbor_counts[point_index] = len(matches)
        return [index for _, index in matches]

    for seed_index in range(len(points)):
        if visited[seed_index]:
            continue
        visited[seed_index] = True
        seed_neighbors = neighbors(seed_index)
        if len(seed_neighbors) < config.minimum_points:
            labels[seed_index] = 0
            continue

        cluster_id += 1
        labels[seed_index] = cluster_id
        roles[seed_index] = ClusterPointRole.CORE
        queue = deque(seed_neighbors)
        queued = set(seed_neighbors)
        while queue:
            candidate_index = queue.popleft()
            if not visited[candidate_index]:
                visited[candidate_index] = True
                candidate_neighbors = neighbors(candidate_index)
                if len(candidate_neighbors) >= config.minimum_points:
                    roles[candidate_index] = ClusterPointRole.CORE
                    for neighbor_index in candidate_neighbors:
                        if neighbor_index not in queued:
                            queue.append(neighbor_index)
                            queued.add(neighbor_index)
            if labels[candidate_index] in (-1, 0):
                labels[candidate_index] = cluster_id
                if roles[candidate_index] is not ClusterPointRole.CORE:
                    roles[candidate_index] = ClusterPointRole.BORDER

    return tuple(
        DynamicClusterResult(
            cluster_id=max(0, labels[index]),
            role=roles[index],
            neighbor_count=neighbor_counts[index],
        )
        for index in range(len(points))
    )


def enrich_rows_with_dynamic_spatial_features(
    rows: Sequence[RowT],
    *,
    adder_config: DynamicAdderConfig | None = None,
    reference_rows: Sequence[Mapping[str, object]] | None = None,
    cluster_config: DynamicClusterConfig | None = None,
) -> tuple[dict[str, object], ...]:
    """Copy rows and expose dynamic values as sampling-rule fields."""

    if adder_config is not None and reference_rows is None:
        raise InvalidSamplingRuleError(
            "dynamic adder calculation requires a user-selected reference layer"
        )
    adders = (
        compute_dynamic_adders(
            rows,
            reference_rows or (),
            config=adder_config,
        )
        if adder_config is not None
        else None
    )
    clusters = (
        compute_dynamic_clusters(rows, config=cluster_config)
        if cluster_config is not None
        else None
    )
    enriched: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        result = dict(row)
        if adders is not None:
            adder = adders[index]
            result[DYNAMIC_ADDER_FIELD] = adder.adder
            result[DYNAMIC_ADDER_DISTANCE_FIELD] = adder.distance
            result[DYNAMIC_ADDER_REFERENCE_INDEX_FIELD] = adder.matched_reference_index
        if clusters is not None:
            cluster = clusters[index]
            result[DYNAMIC_CLUSTER_FIELD] = int(cluster.is_clustered)
            result[DYNAMIC_CLUSTER_ID_FIELD] = cluster.cluster_id
            result[DYNAMIC_CLUSTER_NEIGHBOR_COUNT_FIELD] = cluster.neighbor_count
            result[DYNAMIC_CLUSTER_ROLE_FIELD] = cluster.role.value
        enriched.append(result)
    return tuple(enriched)
