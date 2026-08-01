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
        "SELECT count(*) FROM samples WHERE wafer_x BETWEEN ? AND ? "
        "AND wafer_y BETWEEN ? AND ?",
    ],
)
def test_allows_scoped_read_queries(sql: str) -> None:
    validated = validate_sc_sql(sql)

    assert validated.sql.startswith(("SELECT", "WITH"))


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
