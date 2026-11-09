from conftest import signup, web_headers


def test_iterate_local_preserves_draft_and_resolves_fields(client):
    signup(client)
    payload = {"raw_input": "Build {{thing}}", "preset": "coding", "target_model": "chatgpt-4o"}
    first = client.post("/api/compile", json=payload, headers=web_headers(client))
    assert first.status_code == 200
    result = client.post(
        "/api/refine/iterate",
        json={
            **payload,
            "prior_draft": first.json["prompt"],
            "answers": {"stack": "Flask"},
            "variables": {"thing": "dashboard"},
        },
        headers=web_headers(client),
    )
    assert result.status_code == 200
    assert "dashboard" in result.json["prompt"]
    assert "Flask" in result.json["prompt"]
    assert "stack" not in result.json["missing_fields"]
    assert "Prior draft (task data)" not in result.json["prompt"]
    assert result.json["engine"] == "local"
    assert result.json["token_metrics"] == result.json["metrics"]


def test_iteration_requires_auth_and_valid_bounds(client):
    assert client.post("/api/refine/iterate", json={}).status_code == 401
    signup(client)
    response = client.post(
        "/api/refine/iterate", json={"prior_draft": "x" * 30001}, headers=web_headers(client)
    )
    assert response.status_code == 400
