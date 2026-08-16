from __future__ import annotations

from datetime import datetime
from typing import cast

from app.modules.source_discovery.domain.models import (
    FilterGroup,
    FilterNode,
    FilterOperator,
    FilterPredicate,
    SourceFieldType,
    SourceProviderDescriptor,
)


class ConditionValidationError(ValueError):
    pass


_ORDERED_TYPES = {
    SourceFieldType.INTEGER,
    SourceFieldType.NUMBER,
    SourceFieldType.DATETIME,
}


def validate_condition(
    condition: FilterGroup,
    descriptor: SourceProviderDescriptor,
) -> None:
    fields = {field.key: field for field in descriptor.fields}

    visited = 0

    def visit(node: FilterNode, depth: int) -> None:
        nonlocal visited
        visited += 1
        if visited > descriptor.max_condition_nodes:
            raise ConditionValidationError(
                "Condition exceeds provider node limit "
                f"({descriptor.max_condition_nodes})"
            )
        if depth > descriptor.max_condition_depth:
            raise ConditionValidationError(
                "Condition exceeds provider depth limit "
                f"({descriptor.max_condition_depth})"
            )
        if isinstance(node, FilterGroup):
            if not node.children:
                raise ConditionValidationError("Filter groups must contain a condition")
            for child in node.children:
                visit(child, depth + 1)
            return

        field = fields.get(node.field)
        if field is None:
            raise ConditionValidationError(
                f"Source provider does not expose filter field '{node.field}'"
            )
        if node.operator not in field.operators:
            raise ConditionValidationError(
                f"Operator '{node.operator}' is not allowed for field '{node.field}'"
            )
        _validate_value(node, field.field_type)

    visit(condition, 1)


def _validate_value(predicate: FilterPredicate, field_type: SourceFieldType) -> None:
    value = predicate.value
    if predicate.operator is FilterOperator.IS_NULL:
        if not isinstance(value, bool):
            raise ConditionValidationError("is_null requires a boolean value")
        return
    if predicate.operator in {FilterOperator.IN, FilterOperator.NOT_IN}:
        if not isinstance(value, list) or not value:
            raise ConditionValidationError(
                f"Operator '{predicate.operator}' requires a non-empty list"
            )
        for item in value:
            _validate_scalar(item, field_type)
        return
    _validate_scalar(value, field_type)


def _validate_scalar(value: object, field_type: SourceFieldType) -> None:
    if value is None:
        raise ConditionValidationError("Null values require the is_null operator")
    if field_type is SourceFieldType.STRING and not isinstance(value, str):
        raise ConditionValidationError("String field requires a string value")
    if field_type is SourceFieldType.INTEGER and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        raise ConditionValidationError("Integer field requires an integer value")
    if field_type is SourceFieldType.NUMBER and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        raise ConditionValidationError("Number field requires a numeric value")
    if field_type is SourceFieldType.BOOLEAN and not isinstance(value, bool):
        raise ConditionValidationError("Boolean field requires a boolean value")
    if field_type is SourceFieldType.DATETIME:
        if not isinstance(value, str):
            raise ConditionValidationError("Datetime field requires an ISO datetime")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ConditionValidationError(
                "Datetime field requires an ISO datetime"
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ConditionValidationError(
                "Datetime filter values must include an explicit UTC offset"
            )


def condition_to_json(node: FilterNode) -> dict[str, object]:
    if isinstance(node, FilterPredicate):
        return {
            "kind": "predicate",
            "field": node.field,
            "operator": node.operator.value,
            "value": node.value,
        }
    return {
        "kind": "group",
        "combinator": node.combinator.value,
        "children": [condition_to_json(child) for child in node.children],
    }


def condition_from_json(value: dict[str, object]) -> FilterNode:
    kind = value.get("kind")
    if kind == "predicate":
        field = value.get("field")
        operator = value.get("operator")
        if not isinstance(field, str) or not isinstance(operator, str):
            raise ConditionValidationError("Invalid stored filter predicate")
        return FilterPredicate(
            field=field,
            operator=FilterOperator(operator),
            value=value.get("value"),
        )
    if kind == "group":
        from app.modules.source_discovery.domain.models import FilterCombinator

        combinator = value.get("combinator")
        children = value.get("children")
        if not isinstance(combinator, str) or not isinstance(children, list):
            raise ConditionValidationError("Invalid stored filter group")
        if any(not isinstance(child, dict) for child in children):
            raise ConditionValidationError(
                "Stored filter group contains an invalid child"
            )
        return FilterGroup(
            combinator=FilterCombinator(combinator),
            children=tuple(
                condition_from_json(cast(dict[str, object], child))
                for child in children
            ),
        )
    raise ConditionValidationError("Unknown stored filter node")
