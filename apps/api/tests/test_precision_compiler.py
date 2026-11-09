import pytest
from flask import Flask

from promptengine.compiler import local_compile, precision_output, validate_input
from promptengine.enterprise_security import redact_sensitive
from promptengine.errors import APIError
from promptengine.presets import TARGET_PROFILES


@pytest.mark.parametrize("target", TARGET_PROFILES)
def test_target_variables_and_diagnostics(app, target):
    with app.test_request_context():
        value = validate_input(
            {
                "raw_input": "Create {{subject:dashboard}} for {{audience}}",
                "preset": "coding",
                "target_model": target,
                "variables": {"audience": "engineers"},
            }
        )
        output = precision_output(value, local_compile(value))
        assert "engineers" in output["prompt"]
        assert "{{subject" not in output["prompt"]
        assert 0 <= output["quality_score"] <= 100
        assert sum(output["score_breakdown"].values()) == output["quality_score"]
        assert all(q["id"] and q["suggested_options"] for q in output["clarification_questions"])
        if target == "claude-3-7-sonnet":
            assert "<task>" in output["prompt"]


def test_redaction_and_enterprise_patterns(app):
    with app.app_context():
        app.config["REDACTION_PATTERNS"] = [r"INTERNAL-\d+"]
        try:
            text, count = redact_sensitive(
                "sk-proj-abcdefghijklmno 123-45-6789 4111 1111 1111 1111 INTERNAL-123"
            )
            assert count >= 4
            for secret in ["abcdefghijklmno", "123-45-6789", "4111", "INTERNAL-123"]:
                assert secret not in text
            app.config["REDACTION_PATTERNS"] = ["["]
            with pytest.raises(APIError):
                redact_sensitive("hello")
        finally:
            app.config["REDACTION_PATTERNS"] = []


@pytest.fixture(scope="session")
def app():
    return Flask(__name__)


@pytest.fixture(autouse=True)
def clean_database():
    # These compiler/redaction unit tests never access the database.
    yield
