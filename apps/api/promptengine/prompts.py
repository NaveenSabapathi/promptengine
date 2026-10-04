from flask import Blueprint, g, jsonify, request

from .errors import APIError
from .extensions import db
from .models import SavedPrompt
from .security import json_body, requires_auth, text_field

bp = Blueprint("prompts", __name__, url_prefix="/api/prompts")


def serialize(record):
    return {
        "id": str(record.id),
        "title": record.title,
        "content": record.content,
        "tags": record.tags,
        "created_at": record.created_at.isoformat(),
    }


def prompt_fields(data):
    title = text_field(data, "title", 200)
    content = text_field(data, "content", 50000)
    tags = data.get("tags", [])
    if (
        not isinstance(tags, list)
        or len(tags) > 20
        or any(not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 50 for tag in tags)
    ):
        raise APIError("invalid_tags", "Provide up to 20 tags of 1–50 characters each")
    return {"title": title, "content": content, "tags": sorted(set(tag.strip() for tag in tags))}


def owned_prompt(prompt_id):
    record = db.session.scalar(
        db.select(SavedPrompt).where(
            SavedPrompt.id == prompt_id,
            SavedPrompt.user_id == g.user.id,
        )
    )
    if record is None:
        raise APIError("not_found", "Prompt not found", 404)
    return record


@bp.get("")
@requires_auth("prompts:read")
def list_prompts():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError as exc:
        raise APIError("invalid_pagination", "page and per_page must be integers") from exc
    if page < 1 or page > 10000 or not 1 <= per_page <= 100:
        raise APIError("invalid_pagination", "Use page 1–10000 and per_page 1–100")
    query = db.select(SavedPrompt).where(SavedPrompt.user_id == g.user.id)
    search = request.args.get("q", "").strip()
    if len(search) > 200:
        raise APIError("invalid_search", "Search must contain at most 200 characters")
    if search:
        query = query.where(SavedPrompt.title.icontains(search, autoescape=True))
    records = db.session.scalars(
        query.order_by(
            SavedPrompt.created_at.desc(),
            SavedPrompt.id.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page + 1)
    ).all()
    return jsonify(
        prompts=[serialize(record) for record in records[:per_page]],
        page=page,
        has_more=len(records) > per_page,
    )


@bp.post("")
@requires_auth("prompts:write")
def create_prompt():
    record = SavedPrompt(user_id=g.user.id, **prompt_fields(json_body()))
    db.session.add(record)
    db.session.commit()
    return jsonify(prompt=serialize(record)), 201


@bp.get("/<uuid:prompt_id>")
@requires_auth("prompts:read")
def get_prompt(prompt_id):
    return jsonify(prompt=serialize(owned_prompt(prompt_id)))


@bp.put("/<uuid:prompt_id>")
@requires_auth("prompts:write")
def update_prompt(prompt_id):
    record = owned_prompt(prompt_id)
    for key, value in prompt_fields(json_body()).items():
        setattr(record, key, value)
    db.session.commit()
    return jsonify(prompt=serialize(record))


@bp.delete("/<uuid:prompt_id>")
@requires_auth("prompts:write")
def delete_prompt(prompt_id):
    db.session.delete(owned_prompt(prompt_id))
    db.session.commit()
    return "", 204
