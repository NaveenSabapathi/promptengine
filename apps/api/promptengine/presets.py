from dataclasses import asdict, dataclass
from uuid import UUID

from flask import g, has_request_context

from .errors import APIError

PRESET_VERSION = "2026-10-04.1"
TONES = ("professional", "concise", "friendly", "technical", "persuasive")
MODES = ("Build", "Compact")


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    role: str
    required_fields: dict[str, str]
    optional_fields: dict[str, str]
    output_constraints: tuple[str, ...]

    def public(self):
        return {**asdict(self), "version": PRESET_VERSION}


PRESETS = {
    preset.id: preset
    for preset in (
        Preset(
            "coding",
            "Coding",
            "Senior software engineer",
            {
                "objective": "What must the implementation accomplish?",
                "stack": "Which language, framework and runtime versions should it use?",
                "deliverable": "What files or changes should be delivered?",
            },
            {
                "existing_context": "Existing code, interfaces and repository constraints",
                "constraints": "Security, performance and compatibility requirements",
                "acceptance_criteria": "Observable behavior and tests that define success",
            },
            (
                "Request complete code with exact file paths and no omitted core logic.",
                "Preserve stated interfaces and explain assumptions and setup requirements.",
                "Request relevant tests, error handling and validation; never invent credentials.",
            ),
        ),
        Preset(
            "website_briefs",
            "Website Briefs",
            "Product designer and web architect",
            {
                "objective": "What is the website's primary conversion or business goal?",
                "audience": "Who is the intended audience?",
                "pages": "Which pages and key user journeys are required?",
            },
            {
                "brand": "Brand identity, voice and visual references",
                "stack": "Implementation and hosting constraints",
                "content": "Verified copy, services, assets and contact details",
                "constraints": "Accessibility, SEO, responsive behavior and performance targets",
            },
            (
                "Request page-level hierarchy, calls to action and responsive behavior.",
                "Include accessibility, SEO and implementation acceptance criteria.",
                "Do not invent testimonials, customer logos or business claims.",
            ),
        ),
        Preset(
            "business_proposals",
            "Business Proposals",
            "Senior business proposal consultant",
            {
                "objective": "What outcome or decision should the proposal achieve?",
                "audience": "Who is receiving the proposal?",
                "scope": "What deliverables are included and excluded?",
            },
            {
                "budget": "Currency, pricing and tax assumptions",
                "timeline": "Milestones and delivery dates",
                "company_context": "Verified capabilities and relevant experience",
                "terms": "Payment schedule, dependencies and contractual boundaries",
            },
            (
                "Request an executive summary, scope, deliverables, milestones and next steps.",
                "Distinguish confirmed commercial terms from placeholders or assumptions.",
                "Never invent pricing, certifications, clients or guaranteed results.",
            ),
        ),
        Preset(
            "marketing",
            "Marketing",
            "Senior marketing strategist",
            {
                "objective": "What campaign outcome should be achieved?",
                "audience": "Who is being targeted?",
                "channel": "Which channel and content format will be used?",
            },
            {
                "offer": "Product, offer and verified differentiators",
                "brand": "Brand voice and positioning",
                "budget": "Campaign budget and timing",
                "constraints": "Platform limits, claims, exclusions and success measures",
            },
            (
                "Request channel-specific copy, a clear CTA and measurable success criteria.",
                "Keep claims supported by supplied facts; never invent performance statistics.",
                "Distinguish hypotheses and experiments from guaranteed outcomes.",
            ),
        ),
        Preset(
            "research",
            "Research",
            "Evidence-focused research analyst",
            {
                "objective": "What question should the research answer?",
                "scope": "What topics, geography and boundaries should it cover?",
                "timeframe": "What time period and freshness requirements apply?",
            },
            {
                "sources": "Preferred primary sources and evidence exclusions",
                "audience": "Reader expertise and intended decision",
                "format": "Expected report, comparison or evidence table",
                "constraints": "Methodology, limitations and unresolved questions",
            },
            (
                "Request primary sources, publication dates and links for factual claims.",
                "Separate evidence, inference and uncertainty; never invent citations.",
                "If browsing is unavailable, disclose that limitation "
                "and avoid current-fact claims.",
            ),
        ),
        Preset(
            "professional_comm",
            "Professional Communication",
            "Professional communications editor",
            {
                "objective": "What should the message accomplish?",
                "recipient": "Who is receiving the message?",
                "channel": "Email, chat, letter or another communication format?",
            },
            {
                "context": "Relationship, background and verified facts",
                "call_to_action": "Requested action and any confirmed deadline",
                "constraints": "Length, language and details to include or exclude",
            },
            (
                "Request ready-to-use copy with a clear next action.",
                "Use a subject line for email and adapt length to the channel.",
                "Never invent commitments, deadlines or facts about the recipient.",
            ),
        ),
    )
}


def get_preset(preset_id):
    if preset_id.startswith("custom_") and has_request_context() and g.get("user"):
        from .custom_presets import as_preset, require_custom_access
        from .extensions import db
        from .models import CustomPreset

        require_custom_access()
        cached = g.get("custom_preset")
        if cached and cached.id == preset_id:
            return cached
        try:
            local_id = UUID(preset_id[7:])
        except ValueError as exc:
            raise APIError("invalid_preset", "Invalid custom preset identifier") from exc
        record = db.session.scalar(
            db.select(CustomPreset).where(
                CustomPreset.id == local_id,
                CustomPreset.user_id == g.user.id,
            )
        )
        if not record:
            raise APIError("not_found", "Custom preset not found", 404)
        g.custom_preset = as_preset(record)
        return g.custom_preset
    preset = PRESETS.get(preset_id)
    if preset is None:
        raise APIError("invalid_preset", "Select one of the six available presets")
    return preset
