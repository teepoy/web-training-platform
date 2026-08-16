from __future__ import annotations

import pytest

from app.modules.source_discovery.adapter.sc_provider import (
    SC_SOURCE_PROVIDER_DESCRIPTOR,
)
from app.modules.source_discovery.domain.conditions import (
    ConditionValidationError,
    condition_from_json,
    validate_condition,
)
from app.modules.source_discovery.domain.models import (
    FilterCombinator,
    FilterGroup,
    FilterOperator,
    FilterPredicate,
)


def test_condition_rejects_provider_depth_and_node_overflow() -> None:
    nested = FilterGroup(
        combinator=FilterCombinator.ALL,
        children=(
            FilterGroup(
                combinator=FilterCombinator.ALL,
                children=(
                    FilterGroup(
                        combinator=FilterCombinator.ALL,
                        children=(
                            FilterGroup(
                                combinator=FilterCombinator.ALL,
                                children=(
                                    FilterPredicate(
                                        field="layer_id",
                                        operator=FilterOperator.EQ,
                                        value="M1",
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    with pytest.raises(ConditionValidationError, match="depth limit"):
        validate_condition(nested, SC_SOURCE_PROVIDER_DESCRIPTOR)

    too_many = FilterGroup(
        combinator=FilterCombinator.ANY,
        children=tuple(
            FilterPredicate(
                field="layer_id",
                operator=FilterOperator.EQ,
                value=f"M{index}",
            )
            for index in range(SC_SOURCE_PROVIDER_DESCRIPTOR.max_condition_nodes)
        ),
    )
    with pytest.raises(ConditionValidationError, match="node limit"):
        validate_condition(too_many, SC_SOURCE_PROVIDER_DESCRIPTOR)


def test_stored_condition_rejects_non_object_child() -> None:
    with pytest.raises(ConditionValidationError, match="invalid child"):
        condition_from_json(
            {
                "kind": "group",
                "combinator": "all",
                "children": ["layer_id = M1"],
            }
        )


def test_condition_rejects_raw_or_unregistered_expressions() -> None:
    condition = FilterGroup(
        combinator=FilterCombinator.ALL,
        children=(
            FilterPredicate(
                field="sql",
                operator=FilterOperator.EQ,
                value="drop table datasets",
            ),
        ),
    )
    with pytest.raises(ConditionValidationError, match="does not expose"):
        validate_condition(condition, SC_SOURCE_PROVIDER_DESCRIPTOR)
