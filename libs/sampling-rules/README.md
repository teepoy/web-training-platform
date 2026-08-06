# sampling-rules

`sampling-rules` adds a composable rule pipeline in front of random sampling:

```text
global filter
  -> conditional limits
  -> one group quota/rate rule
  -> total limit
  -> seeded random result
```

The library deliberately does not own persistence, dataset storage, or API models. It
accepts ordinary mappings, produces an inspectable sampling plan, and performs a
seeded draw.

The five rule forms are:

- `GlobalFilterRule`: removes rows that are not globally eligible.
- `ConditionalLimitRule`: caps only the rows matching a condition.
- `GroupQuotaRule` with `COUNT`: picks explicit totals per group.
- `GroupQuotaRule` with `RATIO`: controls the composition of a later total limit.
- `GroupSamplingRateRule`: samples a percentage of each group's own population.
- `TotalLimitRule`: caps the final result without filling missing rows.

Group shortfalls and unlisted groups always require explicit policies.

## Example

```python
from sampling_rules import (
    Condition,
    ConditionOperator,
    ConditionSet,
    GlobalFilterRule,
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
        GlobalFilterRule(
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

result = sample(rows, program=program, seed=7)
```

Use `execute_sampling(...)` when a UI or service also needs the per-rule audit plan.

## SC Review Sampling integration

The production SC Reclassify view exposes the same ordered rule forms through
`ReviewSamplingModal.vue`. Because SC inspection datasets can contain hundreds of
thousands of rows, the web data source compiles enabled conditional, group, and
total stages into one scoped DuckDB query and returns only the sampled defect IDs.
The existing workbench Global Filter remains the shared first stage, and the
selected cohort stays frontend workbench state rather than a server-side column.

The Python package remains useful for bounded in-memory callers and rule semantics;
it does not own the SC data-provider endpoint or persistence.
