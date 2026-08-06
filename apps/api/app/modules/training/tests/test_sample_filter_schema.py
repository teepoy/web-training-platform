from __future__ import annotations

from app.modules.training.port.http.schemas import TrainAndPredictRequest


def test_train_and_predict_preserves_ordered_duplicate_filter_fields() -> None:
    request = TrainAndPredictRequest.model_validate(
        {
            "dataset_id": "dataset-1",
            "trainer_id": "trainer-1",
            "sample_filter": {
                "combinator": "and",
                "items": [
                    {
                        "kind": "condition",
                        "field": "defect_id",
                        "condition": {
                            "filterType": "set",
                            "values": [3, 9],
                            "exclude": True,
                        },
                    },
                    {
                        "kind": "condition",
                        "field": "defect_id",
                        "condition": {
                            "filterType": "set",
                            "values": [7],
                            "exclude": True,
                        },
                    },
                ],
            },
        }
    )

    command = request.to_command(org_id="org-1", created_by="user-1")

    assert command.sample_filter == {
        "combinator": "and",
        "items": [
            {
                "kind": "condition",
                "field": "defect_id",
                "condition": {
                    "filterType": "set",
                    "values": [3.0, 9.0],
                    "exclude": True,
                },
            },
            {
                "kind": "condition",
                "field": "defect_id",
                "condition": {
                    "filterType": "set",
                    "values": [7.0],
                    "exclude": True,
                },
            },
        ],
    }


def test_train_and_predict_preserves_nested_or_group() -> None:
    request = TrainAndPredictRequest.model_validate(
        {
            "dataset_id": "dataset-1",
            "trainer_id": "trainer-1",
            "sample_filter": {
                "combinator": "or",
                "items": [
                    {
                        "kind": "condition",
                        "field": "rough_bin",
                        "condition": {"filterType": "set", "values": [1]},
                    },
                    {
                        "kind": "group",
                        "combinator": "and",
                        "items": [
                            {
                                "kind": "condition",
                                "field": "class_number",
                                "condition": {"filterType": "set", "values": [2]},
                            },
                            {
                                "kind": "condition",
                                "field": "area",
                                "condition": {
                                    "filterType": "number",
                                    "type": "inRange",
                                    "filter": 10,
                                    "filterTo": 20,
                                },
                            },
                        ],
                    },
                ],
            },
        }
    )

    command = request.to_command(org_id="org-1", created_by="user-1")

    assert command.sample_filter is not None
    assert command.sample_filter["combinator"] == "or"
    items = command.sample_filter["items"]
    assert isinstance(items, list)
    second_item = items[1]
    assert isinstance(second_item, dict)
    assert second_item["kind"] == "group"
