from __future__ import annotations

import pytest

from app.modules.sc.data_provider.sql_policy import (
    ScSqlPolicyError,
    validate_sc_sql,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT defect_id FROM samples WHERE rough_bin = ? ORDER BY defect_id",
        "WITH selected AS (SELECT * FROM samples WHERE defect_id = ANY(?)) "
        "SELECT count(*) FROM selected",
        "SELECT r.image_id FROM review_images AS r JOIN samples AS s USING (defect_id)",
        "SELECT * FROM samples WHERE ST_Contains(ST_MakeEnvelope(?, ?, ?, ?), "
        "ST_Point(wafer_x, wafer_y))",
        "SELECT DISTINCT rough_bin FROM samples "
        "WHERE CONTAINS(CAST(rough_bin AS VARCHAR), ?) ORDER BY rough_bin LIMIT ?",
        "SELECT defect_id FROM samples ORDER BY RANDOM() LIMIT ?",
        "SELECT defect_id FROM samples ORDER BY HASH(defect_id, ?) LIMIT ?",
        "SELECT count(*) FROM samples WHERE wafer_x BETWEEN ? AND ? "
        "AND wafer_y BETWEEN ? AND ?",
    ],
)
def test_allows_scoped_read_queries(sql: str) -> None:
    validated = validate_sc_sql(sql)

    assert validated.sql.startswith(("SELECT", "WITH"))


def test_allows_sampling_rule_pipeline_ctes() -> None:
    sql = (
        'WITH "__sc_sampling_base" AS ('
        'SELECT "defect_id", "rough_bin", "class_number", '
        '"rough_bin" IS NOT DISTINCT FROM ? AS "__conditional_match" '
        'FROM samples WHERE "images" > ?), '
        '"__sc_sampling_conditional_ranked" AS ('
        'SELECT *, ROW_NUMBER() OVER (PARTITION BY "__conditional_match" '
        'ORDER BY HASH("defect_id", ?), "defect_id") AS "__conditional_rank" '
        'FROM "__sc_sampling_base"), '
        '"__sc_sampling_conditional" AS ('
        'SELECT * FROM "__sc_sampling_conditional_ranked" '
        'WHERE NOT "__conditional_match" OR "__conditional_rank" <= ?), '
        '"__sc_sampling_group_ranked" AS ('
        'SELECT *, ROW_NUMBER() OVER (PARTITION BY "class_number" '
        'ORDER BY HASH("defect_id", ?), "defect_id") AS "__group_rank", '
        'COUNT(*) OVER (PARTITION BY "class_number") AS "__group_population" '
        'FROM "__sc_sampling_conditional"), '
        '"__sc_sampling_grouped" AS ('
        'SELECT * FROM "__sc_sampling_group_ranked" '
        'WHERE "__group_rank" <= CASE '
        'WHEN "class_number" IS NOT DISTINCT FROM ? '
        'THEN ROUND("__group_population" * ? / 100.0) ELSE 0 END) '
        'SELECT "defect_id" FROM "__sc_sampling_grouped" '
        'ORDER BY HASH("defect_id", ?), "defect_id" LIMIT ?'
    )

    validated = validate_sc_sql(sql)

    assert validated.referenced_views == frozenset({"samples"})


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM samples",
        "CREATE TABLE leaked AS SELECT * FROM samples",
        "COPY samples TO '/tmp/leaked.parquet'",
        "ATTACH '/tmp/other.db' AS other",
        "PRAGMA database_list",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM parquet_scan('s3://bucket/private')",
        "SELECT * FROM information_schema.tables",
        "SELECT getenv('HOME') FROM samples",
        "SELECT * FROM samples; SELECT * FROM review_images",
    ],
)
def test_rejects_unsafe_or_out_of_scope_sql(sql: str) -> None:
    with pytest.raises(ScSqlPolicyError):
        validate_sc_sql(sql)
