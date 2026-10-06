#!/usr/bin/env python3
"""Add feature keys to an existing host without rotating any existing secret."""
import base64
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent.parent
os.umask(0o077)
directory = root / "deploy/secrets"
directory.mkdir(mode=0o700, exist_ok=True)
for name in ("totp_key", "dataset_key"):
    path = directory / name
    if not path.exists():
        with path.open("x") as stream:
            stream.write(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + "\n")
        path.chmod(0o444)
for name in ("mail_hook_secret", "replication_password"):
    path = directory / name
    if not path.exists():
        with path.open("x") as stream:
            stream.write(secrets.token_urlsafe(48) + "\n")
        path.chmod(0o444)
print("Feature keys initialized; existing secrets preserved.")
