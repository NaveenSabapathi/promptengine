import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pyotp
import pytest
from conftest import ORIGIN, PASSWORD, signup, web_headers
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

from promptengine.datasets import process_jobs, scrub
from promptengine.extensions import db
from promptengine.models import (
    Coupon,
    CouponRedemption,
    DatasetJob,
    DatasetPromptLog,
    Entitlement,
    Referral,
    ReferralBalance,
    User,
    WebSession,
)
from promptengine.referrals import grant, paid_conversion
from promptengine.security import now


@pytest.fixture
def feature_keys(app):
    old = {
        k: app.config.get(k)
        for k in ("TOTP_ENCRYPTION_KEY", "DATASET_ENCRYPTION_KEY", "DATASET_ENABLED")
    }
    app.config.update(
        TOTP_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATASET_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        DATASET_ENABLED=True,
    )
    yield
    app.config.update(old)


def user_id(app, email="owner@example.com"):
    with app.app_context():
        return db.session.scalar(db.select(User.id).where(User.email == email))


def admin_client(app, feature_keys):
    client = app.test_client()
    signup(client, "admin@example.com")
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "admin@example.com"))
        user.is_admin, user.totp_enabled = True, True
        session = db.session.scalar(db.select(WebSession).where(WebSession.user_id == user.id))
        session.mfa_at = now()
        db.session.commit()
    return client


def test_signup_cannot_assign_roles(client):
    response = client.post(
        "/api/auth/signup",
        json={"email": "a@example.com", "password": PASSWORD, "is_admin": True},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 400


def test_admin_denies_non_admin_and_stale_mfa(app, client, feature_keys):
    signup(client)
    assert client.get("/api/admin/overview").status_code == 403
    admin = admin_client(app, feature_keys)
    assert admin.get("/api/admin/overview").status_code == 200
    with app.app_context():
        db.session.execute(db.update(WebSession).values(mfa_at=now() - timedelta(minutes=6)))
        db.session.commit()
    assert admin.get("/api/admin/overview").json["error"]["code"] == "mfa_required"


def test_totp_login_replay_and_recovery(app, client, feature_keys):
    signup(client)
    enroll = client.post(
        "/api/security/enroll", json={"password": PASSWORD}, headers=web_headers(client)
    )
    assert enroll.status_code == 200
    from urllib.parse import parse_qs, urlparse

    secret = parse_qs(urlparse(enroll.json["provisioning_uri"]).query)["secret"][0]
    code = pyotp.TOTP(secret).now()
    confirmed = client.post(
        "/api/security/confirm", json={"code": code}, headers=web_headers(client)
    )
    assert confirmed.status_code == 200
    codes = confirmed.json["recovery_codes"]
    assert len(codes) == 8 and len(set(codes)) == 8
    fresh = app.test_client()
    login = {"email": "owner@example.com", "password": PASSWORD}
    assert (
        fresh.post("/api/auth/login", json=login, headers={"Origin": ORIGIN}).json["error"]["code"]
        == "mfa_required"
    )
    assert fresh.get_cookie("access_token_cookie") is None
    assert (
        fresh.post(
            "/api/auth/login", json={**login, "code": code}, headers={"Origin": ORIGIN}
        ).status_code
        == 403
    )
    assert (
        fresh.post(
            "/api/auth/login", json={**login, "code": codes[0]}, headers={"Origin": ORIGIN}
        ).status_code
        == 200
    )
    other = app.test_client()
    assert (
        other.post(
            "/api/auth/login", json={**login, "code": codes[0]}, headers={"Origin": ORIGIN}
        ).status_code
        == 403
    )
    with app.app_context():
        user = db.session.get(User, user_id(app))
        assert len(user.recovery_hashes) == 7
        assert secret not in user.totp_secret and codes[0] not in str(user.recovery_hashes)


def test_coupon_last_use_race(app, feature_keys):
    admin = admin_client(app, feature_keys)
    response = admin.post(
        "/api/admin/coupons",
        json={
            "discount_type": "days_extension",
            "days_granted": 3,
            "max_uses": 1,
            "expires_in_days": 10,
        },
        headers=web_headers(admin),
    )
    assert response.status_code == 201
    code = response.json["code"]
    clients = [app.test_client(), app.test_client()]
    for i, c in enumerate(clients):
        signup(c, f"racer{i}@example.com")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda c: c.post(
                    "/api/rewards/redeem", json={"code": code}, headers=web_headers(c)
                ),
                clients,
            )
        )
    assert sorted(r.status_code for r in responses) == [201, 409]
    with app.app_context():
        assert db.session.scalar(db.select(Coupon.current_uses).where(Coupon.code == code)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(CouponRedemption)) == 1


def test_coupon_per_user_and_expiry(app, client, feature_keys):
    admin = admin_client(app, feature_keys)
    signup(client)
    response = admin.post(
        "/api/admin/coupons",
        json={
            "discount_type": "days_extension",
            "days_granted": 3,
            "max_uses": 5,
            "expires_in_days": 10,
        },
        headers=web_headers(admin),
    )
    code = response.json["code"]
    assert (
        client.post(
            "/api/rewards/redeem", json={"code": code}, headers=web_headers(client)
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/rewards/redeem", json={"code": code}, headers=web_headers(client)
        ).status_code
        == 409
    )
    with app.app_context():
        db.session.execute(db.update(Coupon).values(expires_at=now() - timedelta(days=1)))
        db.session.commit()
    other = app.test_client()
    signup(other, "other@example.com")
    assert (
        other.post(
            "/api/rewards/redeem", json={"code": code}, headers=web_headers(other)
        ).status_code
        == 409
    )


def test_team_isolation_member_permissions_and_revocation(app, client):
    signup(client)
    team = client.post("/api/teams", json={"name": "Acme"}, headers=web_headers(client)).json[
        "team"
    ]
    headers = {**web_headers(client), "X-Team-ID": team["id"]}
    prompt = client.post(
        "/api/prompts", json={"title": "Shared", "content": "Private team task"}, headers=headers
    )
    assert prompt.status_code == 201
    assert client.get("/api/prompts").json["prompts"] == []
    assert len(client.get("/api/prompts", headers={"X-Team-ID": team["id"]}).json["prompts"]) == 1
    member = app.test_client()
    signup(member, "member@example.com")
    invitation = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "member@example.com"},
        headers=web_headers(client),
    )
    token = invitation.json["invitation_url"].split("#invite=")[1]
    assert (
        member.post(
            "/api/teams/accept", json={"token": token}, headers=web_headers(member)
        ).status_code
        == 200
    )
    assert (
        member.post(
            "/api/teams/accept", json={"token": token}, headers=web_headers(member)
        ).status_code
        == 403
    )
    mh = {**web_headers(member), "X-Team-ID": team["id"]}
    assert (
        member.delete("/api/prompts/" + prompt.json["prompt"]["id"], headers=mh).status_code == 403
    )
    assert (
        member.post(
            "/api/teams/" + team["id"] + "/invitations",
            json={"email": "x@example.com"},
            headers=web_headers(member),
        ).status_code
        == 403
    )
    assert member.get("/api/prompts/" + prompt.json["prompt"]["id"]).status_code == 404
    uid = user_id(app, "member@example.com")
    assert (
        client.delete(
            f"/api/teams/{team['id']}/members/{uid}", headers=web_headers(client)
        ).status_code
        == 204
    )
    assert member.get("/api/prompts", headers={"X-Team-ID": team["id"]}).status_code == 403


def test_invitation_is_email_bound(app, client):
    signup(client)
    team = client.post("/api/teams", json={"name": "Acme"}, headers=web_headers(client)).json[
        "team"
    ]
    invite = client.post(
        f"/api/teams/{team['id']}/invitations",
        json={"email": "recipient@example.com"},
        headers=web_headers(client),
    )
    wrong = app.test_client()
    signup(wrong, "wrong@example.com")
    token = invite.json["invitation_url"].split("#invite=")[1]
    assert (
        wrong.post(
            "/api/teams/accept", json={"token": token}, headers=web_headers(wrong)
        ).status_code
        == 403
    )


def test_referral_caps_and_payment_signals(app, client):
    signup(client)
    referrer_id = user_id(app)
    with app.app_context():
        referrer = db.session.get(User, referrer_id)
        referrer.ip_hash, referrer.device_hash, referrer.payment_hash = (
            "ip-a",
            "dev-a",
            "verified-a",
        )
        for i in range(12):
            u = User(email=f"reward{i}@example.com", ip_hash=f"ip-{i}", device_hash=f"dev-{i}")
            db.session.add(u)
            db.session.flush()
            db.session.add(Entitlement(user_id=u.id))
            db.session.flush()
            row = Referral(referrer_id=referrer_id, referee_id=u.id, status="registered")
            db.session.add(row)
            grant(row, "registration")
            grant(row, "conversion")
        db.session.commit()
        balance = db.session.get(ReferralBalance, referrer_id)
        assert balance.registration_days == 30 and balance.conversion_days == 50
        # Missing trusted provider fingerprint must never grant a conversion.
        u = User(email="blocked@example.com", ip_hash="other", device_hash="other-device")
        db.session.add(u)
        db.session.flush()
        db.session.add(Entitlement(user_id=u.id))
        db.session.flush()
        row = Referral(referrer_id=referrer_id, referee_id=u.id, status="registered")
        db.session.add(row)
        db.session.flush()
        paid_conversion(u.id, {"method": "card", "card_id": "not-a-global-fingerprint"})
        assert (
            row.status == "registered"
            and row.blocked_reason == "missing_verified_payment_fingerprint"
        )
        db.session.commit()


def test_dataset_scrubbing_worker_revocation(app, client, feature_keys):
    signup(client)
    payload = {
        "preset_key": "coding",
        "raw_input_context": {"text": "me@example.com +91 98765 43210 api_key=supersecret"},
        "final_prompt_output": "Contact me@example.com",
        "model_response": "sk-proj-abcdefghijklmnopqrstuvwxyz",
        "token_metrics": {"raw_tokens": 10},
    }
    scrubbed = scrub(payload)
    assert (
        "me@example.com" not in str(scrubbed)
        and "supersecret" not in str(scrubbed)
        and "98765" not in str(scrubbed)
    )
    assert (
        client.post(
            "/api/dataset/consent", json={"enabled": True}, headers=web_headers(client)
        ).status_code
        == 200
    )
    with app.app_context():
        user = db.session.get(User, user_id(app))
        import json

        db.session.add(
            DatasetJob(
                user_id=user.id,
                consent_version=user.consent_version,
                encrypted_payload=Fernet(app.config["DATASET_ENCRYPTION_KEY"].encode())
                .encrypt(json.dumps(scrubbed).encode())
                .decode(),
            )
        )
        db.session.commit()
        assert process_jobs() == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(DatasetPromptLog)) == 1
    assert (
        client.post(
            "/api/dataset/consent", json={"enabled": False}, headers=web_headers(client)
        ).status_code
        == 200
    )
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(DatasetPromptLog)) == 0


def test_dataset_default_off_and_export_authorization(app, client):
    signup(client)
    assert (
        client.post(
            "/api/dataset/consent", json={"enabled": True}, headers=web_headers(client)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/dataset/export", json={"reason": "test export"}, headers=web_headers(client)
        ).status_code
        == 403
    )


def test_database_caps_enforced(app, client):
    signup(client)
    with app.app_context():
        db.session.add(
            ReferralBalance(user_id=user_id(app), registration_days=31, conversion_days=0)
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_team_presets_shared_without_personal_leak(app, client):
    signup(client)
    team = client.post("/api/teams", json={"name": "Contracts"}, headers=web_headers(client)).json[
        "team"
    ]
    headers = {**web_headers(client), "X-Team-ID": team["id"]}
    contract = {
        "name": "Shared",
        "role": "Senior engineer",
        "required_fields": {"objective": "Describe the objective"},
        "optional_fields": {},
        "output_constraints": ["Return implementation instructions"],
    }
    saved = client.post("/api/custom-presets", json=contract, headers=headers)
    assert saved.status_code == 201
    preset_id = saved.json["preset"]["id"]
    assert client.get("/api/custom-presets").json["presets"] == []
    personal = client.post(
        "/api/compile",
        json={
            "raw_input": "Build a reliable small app",
            "preset": preset_id,
            "tone": "professional",
            "mode": "Build",
        },
        headers=web_headers(client),
    )
    assert personal.status_code == 404
    shared = client.post(
        "/api/compile",
        json={
            "raw_input": "Build a reliable small app",
            "preset": preset_id,
            "tone": "professional",
            "mode": "Build",
        },
        headers=headers,
    )
    assert shared.status_code == 200


def test_audit_database_append_only(app, client, feature_keys):
    from sqlalchemy.exc import DBAPIError

    from promptengine.models import AuditLog

    admin = admin_client(app, feature_keys)
    uid = user_id(app, "admin@example.com")
    assert (
        admin.post(
            f"/api/admin/users/{uid}/override",
            json={
                "reason": "Support approved",
                "plan_tier": "pro",
                "daily_ai_limit": 150,
                "days": 7,
            },
            headers=web_headers(admin),
        ).status_code
        == 200
    )
    with app.app_context():
        with pytest.raises(DBAPIError):
            db.session.execute(db.delete(AuditLog))
        db.session.rollback()
        assert db.session.scalar(db.select(db.func.count()).select_from(AuditLog)) == 1


def test_totp_recovery_concurrent_use(app, client, feature_keys):
    from promptengine.enterprise_security import hasher

    signup(client)
    uid = user_id(app)
    code = secrets.token_hex(10)
    with app.app_context():
        user = db.session.get(User, uid)
        user.totp_enabled = True
        user.totp_secret = (
            Fernet(app.config["TOTP_ENCRYPTION_KEY"].encode())
            .encrypt(pyotp.random_base32().encode())
            .decode()
        )
        user.recovery_hashes = [hasher.hash(code)]
        db.session.commit()

    def login(_):
        return (
            app.test_client()
            .post(
                "/api/auth/login",
                json={"email": "owner@example.com", "password": PASSWORD, "code": code},
                headers={"Origin": ORIGIN},
            )
            .status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(login, range(2))) == [200, 403]


def test_dataset_export_requires_rating_and_current_consent(app, client, feature_keys):
    import json

    admin = admin_client(app, feature_keys)
    signup(client)
    assert (
        client.post(
            "/api/dataset/consent", json={"enabled": True}, headers=web_headers(client)
        ).status_code
        == 200
    )
    uid = user_id(app)
    with app.app_context():
        for i, rating in enumerate((None, 2, 4)):
            db.session.add(
                DatasetPromptLog(
                    user_id=uid,
                    preset_key="coding",
                    raw_input_context={"task": f"Task {i}"},
                    final_prompt_output=f"Prompt {i}",
                    model_response="{}",
                    token_metrics={},
                    quality_rating=rating,
                )
            )
        db.session.commit()
    response = admin.post(
        "/api/admin/dataset/export",
        json={"reason": "Reviewed training examples"},
        headers=web_headers(admin),
    )
    assert response.status_code == 200
    records = [json.loads(line) for line in response.data.decode().splitlines()]
    assert len(records) == 1 and records[0]["messages"][-1]["content"] == "Prompt 2"
    assert (
        client.post(
            "/api/dataset/consent", json={"enabled": False}, headers=web_headers(client)
        ).status_code
        == 200
    )
    after = admin.post(
        "/api/admin/dataset/export",
        json={"reason": "Consent withdrawal test"},
        headers=web_headers(admin),
    )
    assert after.data == b""
