#!/usr/bin/env python3
"""Initialize host-only configuration; refuse to rotate existing credentials."""

import argparse
import os
from pathlib import Path
import re
import secrets
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, help="Public DNS hostname, without scheme or port")
    parser.add_argument("--self-signed", action="store_true", help="TEST ONLY: generate a self-signed certificate")
    args = parser.parse_args()
    domain = args.domain.lower()
    if len(domain) > 253 or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+",
        domain,
    ):
        parser.error("Use a valid DNS hostname, without a scheme, path, port or wildcard")
    root = Path(__file__).resolve().parent.parent
    env = root / ".deploy.env"
    directory = root / "deploy/secrets"
    if env.exists() or directory.exists():
        parser.error("Deployment is already initialized; edit its existing files instead")
    os.umask(0o077)
    directory.mkdir(mode=0o700)
    for name in ("postgres_password", "postgres_admin_password", "session_secret", "jwt_secret"):
        path = directory / name
        path.write_text(secrets.token_urlsafe(48) + "\n")
        # Compose file-secret mounts retain host modes. Directory is private;
        # each mounted file must be readable by the non-root container user.
        path.chmod(0o444)
    for name in ("openai_key", "google_secret", "microsoft_secret", "razorpay_secret", "razorpay_webhook_secret"):
        path = directory / name
        path.write_text("")
        path.chmod(0o444)
    env.write_text(
        f"PUBLIC_DOMAIN={domain}\nRELEASE_TAG=local\n"
        "HTTP_BIND=0.0.0.0\nHTTP_PORT=80\nHTTPS_BIND=0.0.0.0\nHTTPS_PORT=443\n"
        "TLS_CERT_DIR=./deploy/tls\nGUNICORN_WORKERS=2\nGUNICORN_THREADS=4\n"
        "GOOGLE_CLIENT_ID=\nMICROSOFT_CLIENT_ID=\nMICROSOFT_TENANT=common\n"
        "BILLING_ENABLED=false\nRAZORPAY_KEY_ID=\nRAZORPAY_PRO_PLAN_ID=\n"
        "PRO_PRICE_PAISE=49900\nPRO_DAILY_AI_LIMIT=100\nRAZORPAY_TOTAL_COUNT=120\n"
    )
    tls = root / "deploy/tls"
    tls.mkdir(mode=0o700, exist_ok=True)
    if args.self_signed:
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
             "-days", "2", "-subj", f"/CN={domain}", "-addext", f"subjectAltName=DNS:{domain}",
             "-keyout", str(tls / "privkey.pem"), "-out", str(tls / "fullchain.pem")],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for path in tls.iterdir():
            path.chmod(0o444)
        print("TEST certificate generated; replace it with a trusted certificate before launch.")
    print("Host configuration initialized. No secrets were printed. Follow docs/phase-6.md.")


if __name__ == "__main__":
    main()
