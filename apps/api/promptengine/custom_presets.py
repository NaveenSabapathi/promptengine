import re
from functools import wraps

from flask import Blueprint, current_app, g, jsonify

from .entitlements import effective_entitlement
from .errors import APIError
from .extensions import db
from .models import CustomPreset, Entitlement
from .presets import PRESET_VERSION, Preset
from .security import json_body, requires_auth, text_field

bp = Blueprint("custom_presets", __name__, url_prefix="/api/custom-presets")


def require_custom_access():
    # Free beta exposes this feature; once billing is enabled it requires effective Pro access.
    if current_app.config["BILLING_ENABLED"]:
        tier, _ = effective_entitlement(db.session.get(Entitlement, g.user.id))
        if tier != "pro":
            raise APIError("pro_required", "Custom presets require the Pro plan", 403)


def custom_access(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        require_custom_access()
        return function(*args, **kwargs)

    return wrapped


def as_preset(record):
    return Preset(
        "custom_" + str(record.id),
        record.name,
        record.role,
        record.required_fields,
        record.optional_fields,
        tuple(record.output_constraints),
    )


def validate_contract(data):
    if set(data) - {"name", "role", "required_fields", "optional_fields", "output_constraints"}:
        raise APIError("invalid_preset", "Unexpected custom preset field")
    name, role = text_field(data, "name", 100), text_field(data, "role", 200)
    required, optional = data.get("required_fields"), data.get("optional_fields", {})
    for fields in (required, optional):
        if (
            not isinstance(fields, dict)
            or len(fields) > 6
            or any(
                not isinstance(key, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key)
                or not isinstance(value, str)
                or not 1 <= len(value.strip()) <= 300
                for key, value in fields.items()
            )
        ):
            raise APIError("invalid_preset", "Provide up to six named fields with descriptions")
    if "objective" not in required or set(required) & set(optional):
        raise APIError(
            "invalid_preset", "Require objective and keep required/optional fields separate"
        )
    constraints = data.get("output_constraints")
    if (
        not isinstance(constraints, list)
        or not 1 <= len(constraints) <= 6
        or any(
            not isinstance(value, str) or not 1 <= len(value.strip()) <= 500
            for value in constraints
        )
    ):
        raise APIError("invalid_preset", "Provide 1–6 output constraints of 1–500 characters")
    return {
        "name": name,
        "role": role,
        "required_fields": required,
        "optional_fields": optional,
        "output_constraints": constraints,
    }


def owned(preset_id):
    record = db.session.scalar(
        db.select(CustomPreset).where(
            CustomPreset.id == preset_id,
            CustomPreset.user_id == g.user.id,
        )
    )
    if not record:
        raise APIError("not_found", "Custom preset not found", 404)
    return record


@bp.get("")
@requires_auth("refine")
@custom_access
def list_custom():
    records = db.session.scalars(
        db.select(CustomPreset)
        .where(CustomPreset.user_id == g.user.id)
        .order_by(CustomPreset.created_at.desc())
    ).all()
    return jsonify(
        version=PRESET_VERSION, presets=[as_preset(record).public() for record in records]
    )


@bp.post("")
@requires_auth("refine")
@custom_access
def create_custom():
    fields = validate_contract(json_body())
    # Serialize per-account creation to enforce a bounded number of custom contracts.
    db.session.execute(
        db.select(Entitlement.user_id).where(Entitlement.user_id == g.user.id).with_for_update()
    )
    count = db.session.scalar(
        db.select(db.func.count())
        .select_from(CustomPreset)
        .where(CustomPreset.user_id == g.user.id)
    )
    if count >= 50:
        raise APIError("preset_limit", "Up to 50 custom presets are supported", 409)
    record = CustomPreset(user_id=g.user.id, **fields)
    db.session.add(record)
    db.session.commit()
    return jsonify(preset=as_preset(record).public()), 201


@bp.put("/<uuid:preset_id>")
@requires_auth("refine")
@custom_access
def update_custom(preset_id):
    record = owned(preset_id)
    for key, value in validate_contract(json_body()).items():
        setattr(record, key, value)
    db.session.commit()
    return jsonify(preset=as_preset(record).public())


@bp.delete("/<uuid:preset_id>")
@requires_auth("refine")
def delete_custom(preset_id):
    # Users can delete their data after a downgrade.
    db.session.delete(owned(preset_id))
    db.session.commit()
    return "", 204
