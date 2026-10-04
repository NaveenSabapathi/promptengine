from conftest import signup


def test_public_capabilities_expose_availability_not_secrets(app, client):
    previous = {
        key: app.config[key]
        for key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OPENAI_API_KEY")
    }
    try:
        app.config.update(
            GOOGLE_CLIENT_ID="configured-id",
            GOOGLE_CLIENT_SECRET="private-secret",
            OPENAI_API_KEY="private-key",
        )
        response = client.get("/api/auth/capabilities")
        assert response.status_code == 200
        assert response.json == {
            "providers": {"google": True, "microsoft": False},
            "ai_enabled": True,
        }
        assert "private" not in response.text
        app.config["GOOGLE_CLIENT_SECRET"] = ""
        assert client.get("/api/auth/capabilities").json["providers"]["google"] is False
    finally:
        app.config.update(previous)


def test_me_exposes_only_users_linked_providers(client):
    signup(client)
    assert client.get("/api/auth/me").json["linked_providers"] == []


def test_browser_callback_error_redirects_but_api_keeps_json(client):
    # Unconfigured provider fails before reading a state or attempting a provider call.
    response = client.get(
        "/api/auth/microsoft/callback",
        headers={"Accept": "text/html,application/xhtml+xml,image/webp,*/*;q=0.8"},
    )
    assert response.status_code == 302
    assert response.location == "http://localhost:5173/login?error=provider_not_configured"
    response = client.get("/api/auth/microsoft/callback", headers={"Accept": "application/json"})
    assert response.status_code == 503
    assert response.json["error"]["code"] == "provider_not_configured"
