from __future__ import annotations

import duckdb
import pyarrow as pa
import pytest

from sampling_rules import (
    AdderMatchMode,
    Condition,
    ConditionOperator,
    ConditionSet,
    ConditionalLimitRule,
    DuckDbSamplingSource,
    DynamicAdderConfig,
    DynamicClusterConfig,
    GroupQuotaRule,
    GroupTarget,
    InvalidSamplingRuleError,
    MatchMode,
    QuotaUnit,
    Rounding,
    SamplingProgram,
    ShortfallPolicy,
    TotalLimitRule,
    compile_duckdb_sampling,
    enrich_duckdb_sampling_source,
    execute_duckdb_sampling,
)


def where(field: str, value: object) -> ConditionSet:
    return ConditionSet(
        conditions=(
            Condition(
                field=field,
                operator=ConditionOperator.EQ,
                value=value,
            ),
        ),
        match=MatchMode.ALL,
    )


def test_executes_sampling_directly_over_a_registered_arrow_table() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidate_rows",
        pa.table(
            {
                "row_key": [str(index) for index in range(20)],
                "class_number": [1] * 12 + [2] * 8,
                "is_clustered": [True] * 18 + [False] * 2,
            }
        ),
    )
    program = SamplingProgram(
        rules=(
            ConditionalLimitRule(where=where("is_clustered", True), limit=15),
            GroupQuotaRule(
                group_by=("class_number",),
                unit=QuotaUnit.COUNT,
                targets=(
                    GroupTarget(group=(1,), amount=4),
                    GroupTarget(group=(2,), amount=3),
                ),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.TAKE_AVAILABLE,
            ),
            TotalLimitRule(limit=6),
        )
    )

    execution = execute_duckdb_sampling(
        connection,
        DuckDbSamplingSource.relation(
            "candidate_rows",
            identity_field="row_key",
            output_field="selected_id",
        ),
        program=program,
        seed=42,
        batch_rows=2,
    )
    result = execution.reader.read_all()

    assert result.column_names == ["selected_id"]
    assert result.num_rows == 6
    assert result["selected_id"].to_pylist() == sorted(
        result["selected_id"].to_pylist(),
        key=lambda value: connection.execute(
            "SELECT HASH(?, ?), ?", [value, 42, value]
        ).fetchone(),
    )


def test_compiles_source_parameters_before_sampling_parameters() -> None:
    program = SamplingProgram(rules=(TotalLimitRule(limit=2),))

    compiled = compile_duckdb_sampling(
        DuckDbSamplingSource(
            sql="SELECT row_key FROM candidate_rows WHERE class_number = ?",
            parameters=(3,),
            identity_field="row_key",
            output_field="selected_id",
        ),
        program=program,
        seed=42,
    )

    assert compiled.parameters == (3, 42, 2)
    assert compiled.sql.endswith('ORDER BY HASH("row_key", ?), "row_key" LIMIT ?')


def test_group_shortfall_error_is_enforced_by_duckdb() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidate_rows",
        pa.table({"row_key": ["1"], "class_number": [1]}),
    )
    program = SamplingProgram(
        rules=(
            GroupQuotaRule(
                group_by=("class_number",),
                unit=QuotaUnit.COUNT,
                targets=(GroupTarget(group=(1,), amount=2),),
                others_amount=0,
                rounding=Rounding.NEAREST,
                shortfall=ShortfallPolicy.ERROR,
            ),
        )
    )

    with pytest.raises(duckdb.InvalidInputException, match="available population"):
        execute_duckdb_sampling(
            connection,
            DuckDbSamplingSource.relation(
                "candidate_rows",
                identity_field="row_key",
                output_field="selected_id",
            ),
            program=program,
            seed=42,
            batch_rows=100,
        ).reader.read_all()


def test_rejects_invalid_batch_size_without_an_implicit_default() -> None:
    connection = duckdb.connect(":memory:")
    connection.register("candidate_rows", pa.table({"row_key": ["1"]}))

    with pytest.raises(InvalidSamplingRuleError, match="batch_rows"):
        execute_duckdb_sampling(
            connection,
            DuckDbSamplingSource.relation(
                "candidate_rows",
                identity_field="row_key",
                output_field="selected_id",
            ),
            program=SamplingProgram(rules=(TotalLimitRule(limit=1),)),
            seed=42,
            batch_rows=0,
        )


def test_enriches_registered_arrow_sources_with_dynamic_adders() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "current_rows",
        pa.table(
            {
                "row_key": ["a", "b", "c"],
                "x_nm": [0, 100, 1_000],
                "y_nm": [0, 0, 0],
            }
        ),
    )
    connection.register(
        "reference_rows",
        pa.table(
            {
                "reference_key": ["r1", "r2"],
                "x_nm": [0, 110],
                "y_nm": [0, 0],
            }
        ),
    )
    enriched = enrich_duckdb_sampling_source(
        DuckDbSamplingSource.relation(
            "current_rows",
            identity_field="row_key",
            output_field="selected_id",
        ),
        adder_config=DynamicAdderConfig(
            x_field="x_nm",
            y_field="y_nm",
            radius=50,
            match_mode=AdderMatchMode.ANY_REFERENCE,
        ),
        reference_source=DuckDbSamplingSource.relation(
            "reference_rows",
            identity_field="reference_key",
            output_field="unused",
        ),
    )

    result = connection.execute(
        enriched.sql, list(enriched.parameters)
    ).to_arrow_table()
    rows = {row["row_key"]: row for row in result.to_pylist()}

    assert [rows[key]["dynamic_adder"] for key in ("a", "b", "c")] == [0, 0, 1]
    assert [rows[key]["dynamic_adder_distance"] for key in ("a", "b", "c")] == [
        0.0,
        10.0,
        None,
    ]
    assert [rows[key]["dynamic_adder_reference_index"] for key in ("a", "b", "c")] == [
        0,
        1,
        None,
    ]


def test_enriches_and_samples_dynamic_dbscan_clusters() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidate_rows",
        pa.table(
            {
                "row_key": ["a", "b", "c", "noise"],
                "x_nm": [0.0, 0.0, 0.0, 10.0],
                "y_nm": [0.0, 1.0, 2.0, 10.0],
            }
        ),
    )
    enriched = enrich_duckdb_sampling_source(
        DuckDbSamplingSource.relation(
            "candidate_rows",
            identity_field="row_key",
            output_field="selected_id",
        ),
        cluster_config=DynamicClusterConfig(
            x_field="x_nm",
            y_field="y_nm",
            radius=1.1,
            minimum_points=3,
        ),
    )

    features = connection.execute(
        enriched.sql, list(enriched.parameters)
    ).to_arrow_table()
    execution = execute_duckdb_sampling(
        connection,
        enriched,
        program=SamplingProgram(
            rules=(
                ConditionalLimitRule(
                    where=ConditionSet(
                        conditions=(
                            Condition(
                                field="dynamic_cluster",
                                operator=ConditionOperator.EQ,
                                value=1,
                            ),
                        ),
                        match=MatchMode.ALL,
                    ),
                    limit=2,
                ),
                TotalLimitRule(limit=3),
            )
        ),
        seed=42,
        batch_rows=10,
    )

    rows = {row["row_key"]: row for row in features.to_pylist()}
    order = ("a", "b", "c", "noise")
    assert [rows[key]["dynamic_cluster"] for key in order] == [1, 1, 1, 0]
    assert [rows[key]["dynamic_cluster_id"] for key in order] == [1, 1, 1, 0]
    assert [rows[key]["dynamic_cluster_neighbor_count"] for key in order] == [
        2,
        3,
        2,
        1,
    ]
    assert [rows[key]["dynamic_cluster_role"] for key in order] == [
        "border",
        "core",
        "border",
        "noise",
    ]
    assert execution.reader.read_all().num_rows == 3


def test_dynamic_cluster_component_ids_are_stable_across_disconnected_groups() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "candidate_rows",
        pa.table(
            {
                "row_key": ["a", "b", "c", "d", "e", "f", "noise"],
                "x_nm": [0.0, 0.0, 1.0, 10.0, 10.0, 11.0, 30.0],
                "y_nm": [0.0, 1.0, 0.0, 10.0, 11.0, 10.0, 30.0],
            }
        ),
    )
    enriched = enrich_duckdb_sampling_source(
        DuckDbSamplingSource.relation(
            "candidate_rows",
            identity_field="row_key",
            output_field="selected_id",
        ),
        cluster_config=DynamicClusterConfig(
            x_field="x_nm",
            y_field="y_nm",
            radius=1.5,
            minimum_points=3,
        ),
    )

    first = connection.execute(enriched.sql, list(enriched.parameters)).to_arrow_table()
    second = connection.execute(
        enriched.sql, list(enriched.parameters)
    ).to_arrow_table()
    first_by_key = {
        row["row_key"]: row["dynamic_cluster_id"] for row in first.to_pylist()
    }
    second_by_key = {
        row["row_key"]: row["dynamic_cluster_id"] for row in second.to_pylist()
    }

    assert first_by_key == second_by_key
    assert [first_by_key[key] for key in ("a", "b", "c")] == [1, 1, 1]
    assert [first_by_key[key] for key in ("d", "e", "f")] == [2, 2, 2]
    assert first_by_key["noise"] == 0


def test_combines_adder_and_cluster_over_parameterized_sources() -> None:
    connection = duckdb.connect(":memory:")
    connection.register(
        "current_rows",
        pa.table(
            {
                "row_key": ["a", "b", "c"],
                "x_nm": [0.0, 100.0, 1_000.0],
                "y_nm": [0.0, 0.0, 0.0],
            }
        ),
    )
    connection.register(
        "reference_rows",
        pa.table(
            {
                "reference_key": ["r1"],
                "x_nm": [0.0],
                "y_nm": [0.0],
            }
        ),
    )
    enriched = enrich_duckdb_sampling_source(
        DuckDbSamplingSource(
            sql="SELECT * FROM current_rows WHERE x_nm >= ?",
            parameters=(0.0,),
            identity_field="row_key",
            output_field="selected_id",
        ),
        adder_config=DynamicAdderConfig(
            x_field="x_nm",
            y_field="y_nm",
            radius=50,
            match_mode=AdderMatchMode.ANY_REFERENCE,
        ),
        reference_source=DuckDbSamplingSource(
            sql="SELECT * FROM reference_rows WHERE x_nm >= ?",
            parameters=(0.0,),
            identity_field="reference_key",
            output_field="unused",
        ),
        cluster_config=DynamicClusterConfig(
            x_field="x_nm",
            y_field="y_nm",
            radius=150,
            minimum_points=2,
        ),
    )

    rows = {
        row["row_key"]: row
        for row in connection.execute(enriched.sql, list(enriched.parameters))
        .to_arrow_table()
        .to_pylist()
    }

    assert rows["a"]["dynamic_adder"] == 0
    assert rows["b"]["dynamic_adder"] == 1
    assert rows["a"]["dynamic_cluster_id"] == rows["b"]["dynamic_cluster_id"] == 1
    assert rows["c"]["dynamic_cluster_id"] == 0


def test_rejects_order_dependent_one_to_one_matching_in_table_engine() -> None:
    source = DuckDbSamplingSource.relation(
        "current_rows",
        identity_field="row_key",
        output_field="selected_id",
    )

    with pytest.raises(InvalidSamplingRuleError, match="one_to_one"):
        enrich_duckdb_sampling_source(
            source,
            adder_config=DynamicAdderConfig(
                x_field="x_nm",
                y_field="y_nm",
                radius=50,
                match_mode=AdderMatchMode.ONE_TO_ONE,
            ),
            reference_source=DuckDbSamplingSource.relation(
                "reference_rows",
                identity_field="reference_key",
                output_field="unused",
            ),
        )
