# sampling-rules

`sampling-rules` adds a composable rule pipeline in front of random sampling:

```text
extra filter
  -> conditional limits
  -> one group quota/rate rule
  -> total limit
  -> seeded random result
```

The library deliberately does not own persistence, dataset storage, or API models. It
accepts ordinary mappings, produces an inspectable sampling plan, and performs a
seeded draw.

The four rule forms are:

- `ExtraFilterRule`: implements the optional recursive Extra filter and removes ineligible rows.
- `ConditionalLimitRule`: caps only the rows matching a condition.
- `GroupQuotaRule` with `COUNT`: picks explicit totals per group.
- `GroupQuotaRule` with `RATIO`: samples a percentage of each group's own population.
- `TotalLimitRule`: caps the final result without filling missing rows.

`GroupQuotaRule.others_amount` applies the same count or ratio to every unlisted group.
For example, a sample ratio of `2` means 2% and selects 20 rows from a group of
1,000; it is not a percentage of the final total limit. Group
shortfalls still require an explicit policy.

## Dynamic spatial features

The library can derive runtime-only fields before executing the rule pipeline:

- `compute_dynamic_adders(...)` compares the current map with a user-selected
  reference layer. A current defect with no reference defect inside the
  inclusive radius receives `adder=1`; otherwise it receives `adder=0`.
  `ONE_TO_ONE` consumes a matched reference defect, following the conventional
  semiconductor level-comparison filter. `ANY_REFERENCE` independently checks
  every current defect against the reference map.
- `compute_dynamic_clusters(...)` runs deterministic DBSCAN on the current map.
  Both the neighborhood radius and `minimum_points` are required. It returns
  one-based cluster IDs and core/border/noise roles; noise has cluster ID `0`.
- `enrich_rows_with_dynamic_spatial_features(...)` copies rows and adds
  `dynamic_adder`, `dynamic_cluster`, `dynamic_cluster_id`, match-distance, and
  cluster-audit fields so Extra filter, conditional limit, and group quota rules
  can consume them normally.

Spatial radii use the same unit as the chosen coordinate columns. SC wafer
coordinates are nanometers, so UI values of 50 µm and 500 µm must be passed as
`50_000` and `500_000`, respectively.

## Review Sampling recipes

`sampling_rules.recipes` contains executable examples that return ordinary
`SamplingProgram` values:

```python
from sampling_rules import (
    Rounding,
    adder_count_program,
    clustered_count_program,
    clustered_ratio_program,
    per_die_cap_program,
    prediction_log_quota_program,
)

# At most 50 dynamically clustered defects.
cluster_count = clustered_count_program(50)

# 10% of defects belonging to any dynamic cluster; DBSCAN noise is excluded.
cluster_ratio = clustered_ratio_program(10, rounding=Rounding.NEAREST)

# At most 30 dynamic adders.
adder_count = adder_count_program(30)

# At most five defects from every die.
per_die = per_die_cap_program(
    5,
    die_x_field="index_x",
    die_y_field="index_y",
)

# Per prediction result: x = clip(log10(total), 3, 10), rounded upward.
by_prediction = prediction_log_quota_program(
    {"scratch": 921, "particle": 12_500, "residue": 240_000},
    prediction_field="prediction_label",
    minimum=3,
    maximum=10,
    rounding=Rounding.CEIL,
)
```

Count recipes are caps: a group with fewer than its target contributes every
available row. Prediction populations must come from the same candidate scope
and filters that will be sampled, otherwise the derived target is stale.

## Example

```python
from sampling_rules import (
    Condition,
    ConditionOperator,
    ConditionSet,
    ExtraFilterRule,
    MatchMode,
    SamplingProgram,
    TotalLimitRule,
    sample,
)

rows = [
    {"id": "1", "metadata": {"defect_code": "A"}},
    {"id": "2", "metadata": {"defect_code": "A"}},
    {"id": "3", "metadata": {"defect_code": "B"}},
]

program = SamplingProgram(
    rules=(
        ExtraFilterRule(
            where=ConditionSet(
                conditions=(
                    Condition(
                        field="metadata.defect_code",
                        operator=ConditionOperator.IN,
                        value=("A", "B"),
                    ),
                ),
                match=MatchMode.ALL,
            )
        ),
        TotalLimitRule(limit=2),
    )
)

result = sample(rows, program=program)
```

The default seed is fixed at `42`, matching SC Review Sampling. Use
`execute_sampling(...)` when a UI or service also needs the per-rule audit plan.

## SC Review Sampling integration

The production SC Reclassify view exposes the same ordered rule forms through
`ReviewSamplingModal.vue`. Because SC inspection datasets can contain hundreds of
thousands of rows, the web data source compiles enabled conditional, group, and
total stages into one scoped DuckDB query and returns only the sampled defect IDs.
The optional sampling Extra filter remains the shared first stage, and the
selected cohort stays frontend workbench state rather than a server-side column.

The Python package remains useful for bounded in-memory callers and rule semantics;
it does not own the SC data-provider endpoint or persistence.
