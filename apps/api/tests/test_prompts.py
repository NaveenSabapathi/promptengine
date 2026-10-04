from conftest import signup, web_headers


def test_prompt_crud_isolates_tenants_and_escapes_search(app, client):
    signup(client)
    payload = {"title": "Brief 100%", "content": "Create a launch brief", "tags": ["work", "work"]}
    response = client.post("/api/prompts", json=payload, headers=web_headers(client))
    assert response.status_code == 201
    record = response.json["prompt"]
    assert record["tags"] == ["work"]
    assert client.get("/api/prompts?q=%25").json["prompts"][0]["id"] == record["id"]
    other = app.test_client()
    signup(other, "other@example.com")
    path = "/api/prompts/" + record["id"]
    assert other.get(path).status_code == 404
    assert other.put(path, json=payload, headers=web_headers(other)).status_code == 404
    assert other.delete(path, headers=web_headers(other)).status_code == 404
    assert other.get("/api/prompts").json["prompts"] == []
    updated = client.put(path, json={**payload, "title": "Updated"}, headers=web_headers(client))
    assert updated.json["prompt"]["title"] == "Updated"
    assert client.delete(path, headers=web_headers(client)).status_code == 204
    assert client.get(path).status_code == 404


def test_prompt_validation_and_pagination(client):
    signup(client)
    assert (
        client.post(
            "/api/prompts", json={"title": "", "content": "x"}, headers=web_headers(client)
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/prompts",
            json={"title": "x", "content": "x", "tags": "bad"},
            headers=web_headers(client),
        ).status_code
        == 400
    )
    assert client.get("/api/prompts?per_page=1000").status_code == 400
    assert client.get("/api/prompts?page=hello").status_code == 400
