from fastapi.testclient import TestClient

from app.main import app


def register_tool(
    client: TestClient,
    name: str = "shell.read",
    enabled: bool = True,
) -> dict:
    response = client.post(
        "/tools",
        json={
            "name": name,
            "description": "Read a file from the workspace.",
            "enabled": enabled,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_register_tool() -> None:
    client = TestClient(app)

    tool = register_tool(client)
    get_response = client.get(f"/tools/{tool['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == tool
    assert tool["name"] == "shell.read"
    assert tool["description"] == "Read a file from the workspace."
    assert tool["enabled"] is True
    assert tool["parameters"] == []


def test_register_tool_with_parameters() -> None:
    client = TestClient(app)

    response = client.post(
        "/tools",
        json={
            "name": "artifact.register",
            "description": "Register an artifact reference.",
            "parameters": [
                {"name": "path", "type": "string", "required": True},
                {"name": "metadata", "type": "json", "required": False},
            ],
        },
    )

    assert response.status_code == 200
    tool = response.json()
    assert [parameter["name"] for parameter in tool["parameters"]] == [
        "path",
        "metadata",
    ]
    assert tool["parameters"][0]["type"] == "string"
    assert tool["parameters"][0]["required"] is True
    assert tool["parameters"][1]["type"] == "json"
    assert tool["parameters"][1]["required"] is False


def test_duplicate_tool_rejected() -> None:
    client = TestClient(app)
    register_tool(client, name="shell.read")

    response = client.post(
        "/tools",
        json={
            "name": "shell.read",
            "description": "Duplicate tool.",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Tool already exists: shell.read"


def test_enable_tool() -> None:
    client = TestClient(app)
    tool = register_tool(client, name="shell.write", enabled=False)

    response = client.post(f"/tools/{tool['id']}/enable")

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["updated_at"] is not None


def test_disable_tool() -> None:
    client = TestClient(app)
    tool = register_tool(client, name="shell.write")

    response = client.post(f"/tools/{tool['id']}/disable")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["updated_at"] is not None


def test_list_enabled_tools_only() -> None:
    client = TestClient(app)
    enabled = register_tool(client, name="shell.read", enabled=True)
    register_tool(client, name="shell.write", enabled=False)

    response = client.get("/tools", params={"enabled_only": True})

    assert response.status_code == 200
    assert [tool["id"] for tool in response.json()] == [enabled["id"]]


def test_tool_events_appear_in_trace() -> None:
    client = TestClient(app)
    tool = register_tool(client, name="shell.read", enabled=False)
    client.post(f"/tools/{tool['id']}/enable")
    client.post(f"/tools/{tool['id']}/disable")

    response = client.get("/trace")

    assert response.status_code == 200
    event_types = [event["type"] for event in response.json()]
    assert "tool_registered" in event_types
    assert "tool_enabled" in event_types
    assert "tool_disabled" in event_types


def test_tool_trace_filtering_works() -> None:
    client = TestClient(app)
    tool = register_tool(client, name="shell.read")
    client.post(f"/tools/{tool['id']}/disable")

    response = client.get("/trace", params={"type": "tool_disabled"})

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["type"] == "tool_disabled"
    assert events[0]["metadata"]["tool_id"] == tool["id"]


def test_unknown_tool_returns_404() -> None:
    client = TestClient(app)

    get_response = client.get("/tools/missing-tool")
    enable_response = client.post("/tools/missing-tool/enable")
    disable_response = client.post("/tools/missing-tool/disable")

    assert get_response.status_code == 404
    assert enable_response.status_code == 404
    assert disable_response.status_code == 404
