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
