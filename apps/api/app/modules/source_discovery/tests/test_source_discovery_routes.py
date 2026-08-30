from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.port.http.deps import require_admin


def test_admin_guard_does_not_embed_auth_context_in_connector_body() -> None:
    operation = app.openapi()["paths"]["/api/v1/source-connectors"]["post"]
    schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]
    assert schema_ref == {"$ref": "#/components/schemas/CreateSourceConnectorRequest"}


def test_source_provider_descriptor_is_exposed_as_typed_capabilities() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/source-connectors/providers")

    assert response.status_code == 200, response.text
    providers = response.json()
    sc = next(item for item in providers if item["provider_id"] == "sc")
    assert sc["backfill_time_field"] == "inspection_time"
    assert sc["max_condition_depth"] == 4
    assert sc["max_condition_nodes"] == 40
    layer = next(item for item in sc["fields"] if item["key"] == "layer_id")
    assert layer["field_type"] == "string"
    assert "eq" in layer["operators"]


def test_import_profile_configuration_requires_org_admin() -> None:
    def deny_admin() -> None:
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[require_admin] = deny_admin
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/source-connectors/connector-1/import-profiles",
                json={
                    "name": "bounded import",
                    "settings": {},
                },
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 403
