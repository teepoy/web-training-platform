# sampling-rules

`sampling-rules` owns two composable, deterministic sampling contracts:

- the general-purpose `SamplingProgram` pipeline used by existing recipes; and
- the SC Review `ReviewSamplingProgram`, whose public catalog declares the 17
  product rules shown in the Reclassify UI.

The general-purpose pipeline is:

```text
extra filter
  -> conditional limits
  -> one group quota/rate rule
  -> total limit
  -> seeded random result
```

The library deliberately does not own persistence, dataset storage, or API models.
It owns sampling semantics and provides a production DuckDB compiler/executor for
table-first inputs. The original mapping-based executor remains available for
explicitly bounded callers.

Its rule forms are:

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
- `enrich_duckdb_sampling_source(...)` provides the production table-first path.
  It accepts the current relation plus an optional registered Arrow/reference
  relation and returns another `DuckDbSamplingSource` that can be passed directly
  to `execute_duckdb_sampling(...)`. Radius-sized grid cells bound spatial join
  candidates, and DBSCAN core components use a keyed recursive CTE rather than
  materializing Python rows.

The table engine supports `ANY_REFERENCE` adder semantics. `ONE_TO_ONE` is
explicitly rejected there because its result depends on sequential input order
and consuming matches one row at a time; it remains available only through the
bounded row API. A production caller that requires one-to-one matching must
provide a separate, explicitly ordered matching operation rather than silently
receiving different semantics.

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

## DuckDB table execution

`compile_duckdb_sampling(...)` turns a `SamplingProgram` and a trusted relational
source into one parameterized query. A source can select from a DuckDB table/view
or from an explicitly registered Arrow Table, Dataset, Scanner,
RecordBatchReader, or dataframe. `execute_duckdb_sampling(...)` returns an Arrow
`RecordBatchReader` and requires an explicit batch size.

```python
import duckdb
import pyarrow as pa

from sampling_rules import (
    DuckDbSamplingSource,
    SamplingProgram,
    TotalLimitRule,
    execute_duckdb_sampling,
)

connection = duckdb.connect(":memory:")
connection.register(
    "candidates",
    pa.table({"row_key": ["a", "b", "c"]}),
)
execution = execute_duckdb_sampling(
    connection,
    DuckDbSamplingSource.relation(
        "candidates",
        identity_field="row_key",
        output_field="selected_id",
    ),
    program=SamplingProgram(rules=(TotalLimitRule(limit=2),)),
    seed=42,
    batch_rows=10_000,
)
selected = execution.reader.read_all()
```

## SC Review Sampling integration

The production SC Reclassify view exposes the same ordered rule forms through
`ReviewSamplingModal.vue`. Its dedicated `REVIEW_SAMPLING_RULE_CATALOG` contains
one concrete dataclass for each of the 17 rules. The program is a sequential
pipeline: every filter, selector, distribution draw, and cap receives only the
rows produced by the previous step. Reordering rules therefore intentionally
changes the result. For example, `Maximum per Wafer = 200` followed by `Large
defects by percentage = 10%` can return at most 20 rows per Wafer, while the
reverse order can return up to 200.

The web data source sends only a scoped candidate query and structured program.
The SC data-provider maps that transport shape to `ReviewSamplingProgram`, and
this package compiles the complete program into one production DuckDB query.
Only sampled defect IDs are returned; the service does not materialize candidate
rows in Python.

Result distribution uses exact largest-remainder quotas. The ordinary SC
workbench binds it to Final Class; prediction export may bind the same rule to
Annotation or Prediction after empty results are removed. Target percentages
must total 100%. If a target group is smaller than its quota, all available rows
are selected and the missing quota is not redistributed implicitly.

The optional sampling Extra filter remains part of the candidate query, and the
selected cohort stays frontend workbench state rather than a server-side column.
Dynamic spatial fields remain available to the general-purpose pipeline. Review
Sampling's cluster and repeater rules consume the explicit `cluster_id` and
`repeater_id` columns supplied by the SC candidate relation.
