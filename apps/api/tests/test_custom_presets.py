from datetime import timedelta
from uuid import UUID

from conftest import signup, web_headers

from promptengine.extensions import db
from promptengine.models import Entitlement
from promptengine.security import now

CONTRACT = {
    "name": "Support Reply",
    "role": "Customer support manager",
    "required_fields": {
        "objective": "What should this reply achieve?",
        "recipient": "Who is receiving it?",
    },
    "optional_fields": {"context": "Relevant ticket background"},
    "output_constraints": ["Produce a concise and polite reply; do not invent commitments."],
}


def test_free_beta_custom_preset_can_compile_and_remains_account_private(app, client):
    signup(client)
    response = client.post("/api/custom-presets", json=CONTRACT, headers=web_headers(client))
    assert response.status_code == 201
    preset_id = response.json["preset"]["id"]
    compile_response = client.post(
        "/api/compile",
        json={"raw_input": "Reply about a delayed repair", "preset": preset_id},
        headers=web_headers(client),
    )
    assert compile_response.status_code == 200
    assert "Customer support manager" in compile_response.json["prompt"]
    other = app.test_client()
    signup(other, "other@example.com")
    assert other.get("/api/custom-presets").json["presets"] == []
    assert (
        other.post(
            "/api/compile", json={"raw_input": "x", "preset": preset_id}, headers=web_headers(other)
        ).status_code
        == 404
    )
    path = "/api/custom-presets/" + preset_id[7:]
    assert (
        client.put(
            path, json={**CONTRACT, "name": "Edited"}, headers=web_headers(client)
        ).status_code
        == 200
    )
    assert other.delete(path, headers=web_headers(other)).status_code == 404
    assert client.delete(path, headers=web_headers(client)).status_code == 204


def test_paid_mode_requires_effective_pro_and_expiry_revokes_access(app, client, monkeypatch):
    user_id = UUID(signup(client).json["user"]["id"])
    monkeypatch.setitem(app.config, "BILLING_ENABLED", True)
    assert (
        client.post("/api/custom-presets", json=CONTRACT, headers=web_headers(client)).status_code
        == 403
    )
    with app.app_context():
        entitlement = db.session.get(Entitlement, user_id)
        entitlement.plan_tier, entitlement.daily_ai_limit = "pro", 100
        entitlement.expires_at = now() + timedelta(days=1)
        db.session.commit()
    response = client.post("/api/custom-presets", json=CONTRACT, headers=web_headers(client))
    assert response.status_code == 201
    preset_id = response.json["preset"]["id"]
    with app.app_context():
        entitlement = db.session.get(Entitlement, user_id)
        entitlement.expires_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert (
        client.post(
            "/api/compile",
            json={"raw_input": "Reply", "preset": preset_id},
            headers=web_headers(client),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            "/api/custom-presets/" + preset_id[7:], headers=web_headers(client)
        ).status_code
        == 204
    )


def test_custom_preset_validation_requires_objective_and_distinct_fields(client):
    signup(client)
    bad = {**CONTRACT, "required_fields": {"other": "Question"}}
    assert (
        client.post("/api/custom-presets", json=bad, headers=web_headers(client)).status_code == 400
    )
    bad = {**CONTRACT, "optional_fields": {"objective": "Duplicate"}}
    assert (
        client.post("/api/custom-presets", json=bad, headers=web_headers(client)).status_code == 400
    )


def test_migration_downgrade_preserves_numeric_history_with_long_custom_ids(app, client):
    from flask_migrate import downgrade, upgrade

    from promptengine.models import GenerationMetric

    signup(client)
    response = client.post("/api/custom-presets", json=CONTRACT, headers=web_headers(client))
    preset_id = response.json["preset"]["id"]
    generated = client.post(
        "/api/compile",
        json={"raw_input": "Reply politely", "preset": preset_id},
        headers=web_headers(client),
    )
    assert generated.status_code == 200
    metrics_id = UUID(generated.json["generation_id"])
    with app.app_context():
        db.session.remove()
        downgrade(directory="migrations", revision="b65352810b54")
        assert (
            db.session.execute(
                db.text("SELECT preset_id FROM generation_metrics WHERE id = :id"),
                {"id": metrics_id},
            ).scalar_one()
            == "custom_archived"
        )
        db.session.remove()
        upgrade(directory="migrations")
        assert (
            db.session.get(GenerationMetric, metrics_id).raw_tokens
            == generated.json["metrics"]["raw_tokens"]
        )
