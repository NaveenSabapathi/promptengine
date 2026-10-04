#!/usr/bin/env python3
"""Exercise the real HTTPS deployment on an isolated CI/test stack."""

import http.client
import http.cookiejar
import json
from pathlib import Path
import re
import ssl
import subprocess
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "--env-file", ".deploy.env", "-f", "docker-compose.yml"]
DOMAIN = "promptengine.test"
ORIGIN = f"https://{DOMAIN}"
COOKIE_JAR = http.cookiejar.CookieJar()
CONTEXT = ssl.create_default_context(cafile=str(ROOT / "deploy/tls/fullchain.pem"))
OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPCookieProcessor(COOKIE_JAR),
    urllib.request.HTTPSHandler(context=CONTEXT),
)


def request(path, data=None, *, headers=None, csrf=True, expected=200):
    values = {"Origin": ORIGIN, **(headers or {})}
    if data is not None:
        values["Content-Type"] = "application/json"
        if csrf:
            token = next((c.value for c in COOKIE_JAR if c.name == "csrf_access_token"), "")
            values["X-CSRF-TOKEN"] = token
    call = urllib.request.Request(
        ORIGIN + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=values,
    )
    try:
        response = OPENER.open(call, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read().decode()
        assert response.status == expected, (path, response.status, body)
        return response.headers, body


def command(*args, input=None):
    return subprocess.check_output([*COMPOSE, *args], cwd=ROOT, input=input, text=True)


def main():
    # This script is deliberately locked to the test hostname and disposable CI DB.
    config = json.loads(command("config", "--format", "json"))
    assert config["services"]["web"]["environment"]["PUBLIC_DOMAIN"] == DOMAIN
    assert "ports" not in config["services"]["db"]
    assert "ports" not in config["services"]["api"]
    privileges = command("exec", "-T", "db", "psql", "-U", "postgres", "-d", "postgres", "-tAc", "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication FROM pg_roles WHERE rolname='promptengine'")
    assert privileges.strip() == "f"
    request("/api/health/ready")
    connection = http.client.HTTPConnection(DOMAIN, 80, timeout=10)
    connection.request("GET", "/workspace?check=redirect")
    response = connection.getresponse()
    assert response.status == 308
    assert response.getheader("Location") == ORIGIN + "/workspace?check=redirect"
    response.read()
    connection.close()

    headers, html = request("/workspace")
    assert '<div id="root">' in html
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "max-age=31536000" in headers["Strict-Transport-Security"]
    asset = re.search(r'src="(/assets/[^\"]+\.js)"', html).group(1)
    headers, _ = request(asset)
    assert "max-age=31536000" in headers["Cache-Control"]
    request("/assets/does-not-exist.js", expected=404)
    request("/.env", expected=404)

    request("/api/auth/signup", {"email": "deploy-ci@example.com", "password": "deployment-ci-only-password"}, expected=201)
    session = next(c for c in COOKIE_JAR if c.name == "access_token_cookie")
    assert session.secure and session.has_nonstandard_attr("HttpOnly")
    request("/api/auth/me")
    request("/api/prompts", {"title": "No CSRF", "content": "Denied"}, csrf=False, expected=401)
    payload = {"raw_input": "Build a PostgreSQL dashboard", "preset": "coding", "tone": "professional", "mode": "Build", "fields": {}}
    _, compiled = request("/api/compile", payload)
    prompt = json.loads(compiled)["prompt"]
    assert "PostgreSQL" in prompt
    request("/api/refine", payload, expected=503)  # Provider intentionally disabled in CI.
    _, saved = request("/api/prompts", {"title": "Restore proof", "content": prompt, "tags": ["deployment"]}, expected=201)
    prompt_id = json.loads(saved)["prompt"]["id"]
    _, listing = request("/api/prompts?q=Restore")
    assert json.loads(listing)["prompts"][0]["id"] == prompt_id
    request("/api/auth/capabilities?code=DO_NOT_LOG_CI_CODE")
    for index in range(4):
        request("/api/auth/signup", {}, headers={"X-Forwarded-For": f"198.51.100.{index}"}, expected=400)
    request("/api/auth/signup", {}, headers={"X-Forwarded-For": "198.51.100.99"}, expected=429)
    assert "DO_NOT_LOG_CI_CODE" not in command("logs", "--no-color", "api", "web")

    # Real custom-format backup/restore after deleting a saved prompt. No mocks.
    backup = subprocess.check_output(["sh", "deploy/backup.sh"], cwd=ROOT, text=True).strip()
    command("exec", "-T", "db", "psql", "-U", "promptengine", "-d", "promptengine", "-c", "DELETE FROM saved_prompts")
    subprocess.run(["sh", "deploy/restore.sh", "--replace-database", str(ROOT / backup)], cwd=ROOT, check=True)
    count = command("exec", "-T", "db", "psql", "-U", "promptengine", "-d", "promptengine", "-tAc", "SELECT count(*) FROM saved_prompts")
    assert count.strip() == "1"
    command("up", "-d", "--wait", "api", "web")
    request(f"/api/prompts/{prompt_id}")
    # API container replacement must recover through Docker DNS in Nginx.
    command("up", "-d", "--no-deps", "--force-recreate", "--wait", "api")
    import time
    for attempt in range(15):
        try:
            request("/api/health/ready")
            break
        except AssertionError:
            if attempt == 14:
                raise
            time.sleep(1)
    print("HTTPS, SPA/assets, secure auth/CSRF, compiler, rate limits, log redaction, backup/restore and API replacement passed.")


if __name__ == "__main__":
    main()
