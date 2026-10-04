import json
from dataclasses import dataclass

import httpx
from flask import current_app
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .compiler import compile_messages
from .errors import APIError
from .presets import get_preset

# Use the supported JSON Schema subset; length/semantic checks run on the API too.
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "prompt": {"type": "string"},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "clarification_questions": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["prompt", "missing_fields", "clarification_questions", "assumptions"],
}


class RefinedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt: str = Field(min_length=1, max_length=30000)
    missing_fields: list[str] = Field(max_length=6)
    clarification_questions: list[str] = Field(max_length=6)
    assumptions: list[str] = Field(max_length=6)


@dataclass(frozen=True)
class ProviderResult:
    output: dict
    model: str
    input_tokens: int | None
    output_tokens: int | None


def require_provider():
    if not current_app.config["OPENAI_API_KEY"]:
        raise APIError(
            "ai_not_configured", "AI refinement is unavailable; use local compiling", 503
        )


def refine_with_openai(value):
    require_provider()
    compiled = compile_messages(value)
    try:
        # Disable automatic retries: one admitted generation makes at most one provider request.
        with OpenAI(
            api_key=current_app.config["OPENAI_API_KEY"],
            max_retries=0,
            timeout=httpx.Timeout(current_app.config["OPENAI_TIMEOUT_SECONDS"], connect=5),
        ) as client:
            response = client.chat.completions.create(
                model=current_app.config["OPENAI_MODEL"],
                messages=[
                    {"role": "system", "content": compiled.system_prompt},
                    {"role": "user", "content": compiled.user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "refined_prompt",
                        "strict": True,
                        "schema": OUTPUT_SCHEMA,
                    },
                },
                temperature=0.2,
                max_completion_tokens=current_app.config["OPENAI_MAX_OUTPUT_TOKENS"],
                store=False,
            )
    except APITimeoutError as exc:
        raise APIError("ai_timeout", "AI provider timed out. Please try again", 503) from exc
    except (RateLimitError, APIConnectionError) as exc:
        raise APIError(
            "ai_unavailable", "AI provider is temporarily unavailable. Try again", 503
        ) from exc
    except (AuthenticationError, PermissionDeniedError, BadRequestError) as exc:
        raise APIError(
            "ai_configuration_error", "AI refinement is unavailable; contact support", 503
        ) from exc
    except APIStatusError as exc:
        raise APIError(
            "ai_unavailable", "AI provider is temporarily unavailable. Try again", 503
        ) from exc
    if not isinstance(response.choices, list) or len(response.choices) != 1:
        raise APIError("ai_invalid_response", "AI returned an invalid response. Try again", 502)
    choice = response.choices[0]
    if (
        choice.message is None
        or not isinstance(response.model, str)
        or not 1 <= len(response.model) <= 128
    ):
        raise APIError("ai_invalid_response", "AI returned an invalid response. Try again", 502)
    if choice.message.refusal or choice.finish_reason == "content_filter":
        raise APIError("ai_refused", "AI provider could not refine this request", 422)
    if choice.finish_reason != "stop" or not choice.message.content:
        raise APIError("ai_incomplete", "AI response was incomplete. Try a shorter task", 502)
    try:
        output = RefinedOutput.model_validate(json.loads(choice.message.content)).model_dump()
        required = get_preset(value.preset).required_fields
        if (
            not output["prompt"].strip()
            or output["prompt"].strip().startswith("```")
            or set(output["missing_fields"]) - set(required)
            or len(set(output["missing_fields"])) != len(output["missing_fields"])
            or any(
                not 1 <= len(text.strip()) <= 1000
                for key in (
                    "clarification_questions",
                    "assumptions",
                )
                for text in output[key]
            )
        ):
            raise ValueError("Invalid compiler output")
    except (ValueError, ValidationError) as exc:
        raise APIError(
            "ai_invalid_response", "AI returned an invalid response. Try again", 502
        ) from exc
    usage = response.usage
    return ProviderResult(
        output,
        response.model,
        usage.prompt_tokens if usage else None,
        usage.completion_tokens if usage else None,
    )
