import secrets
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.dialects.postgresql import insert

from .auth import normalized_email
from .enterprise_security import audit
from .errors import APIError
from .extensions import db
from .models import MailOutbox, Team, TeamInvitation, TeamMembership
from .security import digest, json_body, now, rate_limit, requires_auth, text_field, uuid_field

bp = Blueprint("teams", __name__, url_prefix="/api/teams")


def resolve_team():
    g.team_id, g.team_role = None, None
    value = request.headers.get("X-Team-ID")
    if value:
        if g.auth_kind != "web":
            raise APIError("web_session_required", "Shared workspaces require a web session", 403)
        db.session.execute(db.select(Team).where(Team.id == uuid_field(value)).with_for_update())
        member = db.session.get(TeamMembership, (uuid_field(value), g.user.id))
        if not member:
            raise APIError("team_access_denied", "Workspace membership required", 403)
        g.team_id, g.team_role = member.team_id, member.role


def asset_scope(model):
    if g.get("team_id"):
        return model.team_id == g.team_id
    return db.and_(model.team_id.is_(None), model.user_id == g.user.id)


def manage_assets():
    if g.get("team_id") and g.team_role not in {"OWNER", "ADMIN"}:
        raise APIError("team_admin_required", "Workspace owner or administrator required", 403)


def membership(team_id, manage=False):
    # Lock the parent team for membership mutations; removal and invitation acceptance
    # use the same order so permission checks cannot race role changes.
    team = db.session.scalar(db.select(Team).where(Team.id == team_id).with_for_update())
    record = db.session.get(TeamMembership, (team_id, g.user.id))
    if not team or not record:
        raise APIError("not_found", "Workspace not found", 404)
    if manage and record.role not in {"OWNER", "ADMIN"}:
        raise APIError("team_admin_required", "Workspace owner or administrator required", 403)
    return record


@bp.get("")
@requires_auth(web_only=True)
def list_teams():
    rows = db.session.execute(
        db.select(Team, TeamMembership.role)
        .join(TeamMembership)
        .where(TeamMembership.user_id == g.user.id)
    ).all()
    return jsonify(teams=[{"id": str(t.id), "name": t.name, "role": role} for t, role in rows])


@bp.post("")
@requires_auth(web_only=True)
def create_team():
    rate_limit("team_create", 5, seconds=3600, identity=str(g.user.id))
    team = Team(name=text_field(json_body(), "name", 100))
    db.session.add(team)
    db.session.flush()
    db.session.add(TeamMembership(team_id=team.id, user_id=g.user.id, role="OWNER"))
    audit("team.created", team.id)
    db.session.commit()
    return jsonify(team={"id": str(team.id), "name": team.name, "role": "OWNER"}), 201


@bp.get("/<uuid:team_id>/members")
@requires_auth(web_only=True)
def members(team_id):
    membership(team_id)
    from .models import User

    rows = (
        db.session.execute(
            db.select(User.id, User.email, TeamMembership.role)
            .join(TeamMembership)
            .where(TeamMembership.team_id == team_id)
        )
        .mappings()
        .all()
    )
    return jsonify(members=[{**dict(row), "id": str(row["id"])} for row in rows])


@bp.post("/<uuid:team_id>/invitations")
@requires_auth(web_only=True)
def invite(team_id):
    rate_limit("team_invite", 20, seconds=3600, identity=str(g.user.id))
    membership(team_id, manage=True)
    data = json_body()
    role = data.get("role", "MEMBER")
    if role not in {"MEMBER", "ADMIN"}:
        raise APIError("invalid_role", "Invite a MEMBER or ADMIN")
    # Only owners can assign administrators, preventing admin-to-admin escalation.
    if role == "ADMIN" and membership(team_id).role != "OWNER":
        raise APIError("owner_required", "Only the owner can invite administrators", 403)
    email = normalized_email(data.get("email"))
    token = secrets.token_urlsafe(32)
    invite = TeamInvitation(
        team_id=team_id,
        email=email,
        role=role,
        token_hash=digest(token),
        expires_at=now() + timedelta(days=7),
    )
    db.session.add(invite)
    url = current_app.config["WEB_ORIGIN"] + "/teams#invite=" + token
    db.session.add(
        MailOutbox(recipient=email, subject="PromptLogic workspace invitation", body=url)
    )
    audit("team.invited", team_id, {"role": role})
    db.session.commit()
    return jsonify(invitation_url=url, expires_at=invite.expires_at.isoformat()), 201


@bp.post("/accept")
@requires_auth(web_only=True)
def accept():
    rate_limit("team_accept", 10, seconds=300, identity=str(g.user.id))
    token = text_field(json_body(), "token", 100, 20)
    probe = db.session.scalar(
        db.select(TeamInvitation).where(TeamInvitation.token_hash == digest(token))
    )
    if not probe:
        raise APIError("invalid_invitation", "Invitation is unavailable", 404)
    db.session.execute(db.select(Team).where(Team.id == probe.team_id).with_for_update())
    record = db.session.scalar(
        db.select(TeamInvitation)
        .where(TeamInvitation.id == probe.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record.email != g.user.email or record.accepted_at or record.expires_at <= now():
        raise APIError(
            "invalid_invitation", "Invitation is expired, used, or belongs to another account", 403
        )
    db.session.execute(
        insert(TeamMembership)
        .values(team_id=record.team_id, user_id=g.user.id, role=record.role)
        .on_conflict_do_nothing()
    )
    record.accepted_at = now()
    audit("team.joined", record.team_id)
    db.session.commit()
    return jsonify(ok=True)


@bp.delete("/<uuid:team_id>/members/<uuid:user_id>")
@requires_auth(web_only=True)
def remove_member(team_id, user_id):
    actor = membership(team_id, manage=True)
    target = db.session.get(TeamMembership, (team_id, user_id))
    if not target:
        raise APIError("not_found", "Member not found", 404)
    if target.role == "OWNER" or (target.role == "ADMIN" and actor.role != "OWNER"):
        raise APIError("owner_required", "This membership requires the owner", 403)
    db.session.delete(target)
    audit("team.member_revoked", team_id, {"user_id": str(user_id)})
    db.session.commit()
    return "", 204
