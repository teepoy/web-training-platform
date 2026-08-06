from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class ScSqlPolicyError(ValueError):
    """Raised when caller SQL exceeds the read-only scoped query contract."""


_SCOPE_VIEWS = frozenset({"samples", "review_images"})
_ALLOWED_FUNCTIONS = frozenset(
    {
        "ABS",
        "APPROX_COUNT_DISTINCT",
        "APPROX_QUANTILE",
        "ARRAY_AGG",
        "AVG",
        "CASE",
        "CAST",
        "CEIL",
        "COALESCE",
        "CONCAT",
        "CONTAINS",
        "COUNT",
        "DATE_PART",
        "DENSE_RANK",
        "ENDS_WITH",
        "FLOOR",
        "GREATEST",
        "HASH",
        "HISTOGRAM",
        "IF",
        "ISFINITE",
        "ISNAN",
        "LAG",
        "LEAD",
        "LEAST",
        "LENGTH",
        "LIST",
        "LOWER",
        "MAX",
        "MEDIAN",
        "MIN",
        "NULLIF",
        "QUANTILE",
        "QUANTILE_CONT",
        "RAND",
        "RANDOM",
        "RANK",
        "REGEXP_MATCHES",
        "ROUND",
        "ROW_NUMBER",
        "STARTS_WITH",
        "STDDEV",
        "STDDEV_POP",
        "STDDEV_SAMP",
        "STRING_AGG",
        "SUM",
        "UPPER",
        "VARIANCE",
        "VAR_POP",
        "VAR_SAMP",
        "ST_CONTAINS",
        "ST_DISTANCE",
        "ST_INTERSECTS",
        "ST_MAKEENVELOPE",
        "ST_POINT",
        "ST_WITHIN",
        "ST_X",
        "ST_Y",
    }
)
_FORBIDDEN_NODES = (
    exp.Alter,
    exp.Attach,
    exp.Command,
    exp.Copy,
    exp.Create,
    exp.Delete,
    exp.Detach,
    exp.Drop,
    exp.Insert,
    exp.Merge,
    exp.Pragma,
    exp.Transaction,
    exp.Update,
    exp.Use,
)


@dataclass(frozen=True)
class ValidatedScSql:
    sql: str
    referenced_views: frozenset[str]


def validate_sc_sql(sql: str) -> ValidatedScSql:
    try:
        statements = parse(sql, read="duckdb")
    except ParseError as exc:
        raise ScSqlPolicyError(f"invalid DuckDB SQL: {exc}") from exc

    if len(statements) != 1:
        raise ScSqlPolicyError("exactly one SQL statement is required")
    statement = statements[0]
    if statement is None or not isinstance(statement, exp.Query):
        raise ScSqlPolicyError("only SELECT or WITH ... SELECT queries are allowed")

    forbidden = next(
        (node for node in statement.walk() if isinstance(node, _FORBIDDEN_NODES)),
        None,
    )
    if forbidden is not None:
        raise ScSqlPolicyError(f"forbidden SQL operation: {forbidden.key.upper()}")

    cte_names = {
        cte.alias_or_name.casefold()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    referenced_views: set[str] = set()
    for table in statement.find_all(exp.Table):
        if table.catalog or table.db:
            raise ScSqlPolicyError("catalog- and schema-qualified tables are forbidden")
        if not isinstance(table.this, exp.Identifier):
            raise ScSqlPolicyError("table functions and external scans are forbidden")
        table_name = table.name.casefold()
        if table_name in cte_names:
            continue
        if table_name not in _SCOPE_VIEWS:
            raise ScSqlPolicyError(f"table is outside this scope: {table.name}")
        referenced_views.add(table_name)

    for function in statement.find_all(exp.Func):
        if isinstance(function, exp.Binary):
            continue
        function_name = function.sql_name().upper()
        if function_name == "ANONYMOUS":
            function_name = function.name.upper()
        if function_name == "UNNEST":
            if not all(
                isinstance(argument, (exp.Placeholder, exp.Parameter))
                for argument in function.expressions
            ):
                raise ScSqlPolicyError("UNNEST only accepts bound parameters")
            continue
        if function_name not in _ALLOWED_FUNCTIONS:
            raise ScSqlPolicyError(f"function is not allowed: {function_name}")

    return ValidatedScSql(
        sql=statement.sql(dialect="duckdb"),
        referenced_views=frozenset(referenced_views),
    )
