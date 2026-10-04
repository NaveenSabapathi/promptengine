import os

import pytest

from promptengine.environment import SECRET_NAMES, load_file_secrets


@pytest.fixture(autouse=True)
def isolated_secret_environment(monkeypatch):
    for name in (*SECRET_NAMES, "POSTGRES_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name + "_FILE", raising=False)


def test_file_secret_and_optional_blank(tmp_path, monkeypatch):
    path = tmp_path / "secret"
    path.write_text("safe-test-secret\n")
    monkeypatch.setenv("SECRET_KEY_FILE", str(path))
    empty = tmp_path / "empty"
    empty.write_text("")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(empty))
    load_file_secrets()
    assert os.environ["SECRET_KEY"] == "safe-test-secret"
    assert os.environ["OPENAI_API_KEY"] == ""


def test_database_password_is_url_encoded(tmp_path, monkeypatch):
    path = tmp_path / "password"
    path.write_text("a@b:/?&%#")
    monkeypatch.setenv("POSTGRES_PASSWORD_FILE", str(path))
    load_file_secrets()
    assert os.environ["DATABASE_URL"] == (
        "postgresql+psycopg://promptengine:a%40b%3A%2F%3F%26%25%23@db:5432/promptengine"
    )


def test_conflicting_secret_sources_fail_without_leaking(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "do-not-expose")
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="Configure only SECRET_KEY") as error:
        load_file_secrets()
    assert "do-not-expose" not in str(error.value)


def test_missing_secret_file_has_safe_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "sensitive-path"))
    with pytest.raises(RuntimeError, match="Cannot read SECRET_KEY_FILE") as error:
        load_file_secrets()
    assert "sensitive-path" not in str(error.value)


def test_multiline_secret_rejected(tmp_path, monkeypatch):
    path = tmp_path / "secret"
    path.write_text("first\nsecond")
    monkeypatch.setenv("JWT_SECRET_KEY_FILE", str(path))
    with pytest.raises(RuntimeError, match="single line"):
        load_file_secrets()
