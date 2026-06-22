""" Renderer for EmailAuto."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.template import Context, Template, TemplateSyntaxError

from emailauto.core.exceptions import MissingTemplateVariable, TemplateRenderError
from emailauto.core.results import RenderedEmail
from emailauto.templates.models import EmailTemplate


@dataclass(frozen=True)
class TemplateSnapshot:
    """An immutable, point-in-time copy of a template, used to render an outbox row.

    Rendering from this snapshot (captured when the row is created) rather than from the
    live EmailTemplate guarantees a queued email cannot change if the template is edited
    after the fact.
    """

    subject_template: str
    body_template: str
    body_format: str = "text"
    required_variables: list[str] = field(default_factory=list)

    @classmethod
    def from_outbox(cls, outbox) -> TemplateSnapshot:
        return cls(
            subject_template=outbox.subject_snapshot,
            body_template=outbox.body_snapshot,
            body_format=outbox.body_format,
            required_variables=list(outbox.required_variables_snapshot or []),
        )


def build_render_context(*, recipient, campaign, campaign_run=None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    # Custom fields are merged first so the reserved keys below always win: a recipient
    # whose custom_fields contains "campaign"/"recipient"/"run" cannot shadow them.
    context.update(recipient.custom_fields or {})
    context.update(
        {
            "recipient": {
                "id": recipient.id,
                "email": recipient.email,
                "name": recipient.name,
                "custom_fields": recipient.custom_fields or {},
            },
            "campaign": {"id": campaign.id, "name": campaign.name},
            "run": {"id": getattr(campaign_run, "id", None), "run_key": getattr(campaign_run, "run_key", "")},
            "fields": recipient.custom_fields or {},
        }
    )
    if extra:
        context.update(extra)
    return context


def _resolve(context: dict[str, Any], dotted_name: str) -> Any:
    current: Any = context
    for part in dotted_name.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise MissingTemplateVariable(dotted_name)
    if current in (None, ""):
        raise MissingTemplateVariable(dotted_name)
    return current


def validate_required_variables(email_template: EmailTemplate | TemplateSnapshot, context: dict[str, Any]) -> None:
    for variable in email_template.required_variables or []:
        _resolve(context, variable)


def render_template(
    *,
    email_template: EmailTemplate | TemplateSnapshot,
    recipient,
    campaign,
    campaign_run=None,
    idempotency_key: str,
    extra: dict[str, Any] | None = None,
) -> RenderedEmail:
    context = build_render_context(recipient=recipient, campaign=campaign, campaign_run=campaign_run, extra=extra)
    validate_required_variables(email_template, context)
    try:
        subject = Template(email_template.subject_template).render(Context(context)).strip()
        body = Template(email_template.body_template).render(Context(context))
    except TemplateSyntaxError as exc:
        raise TemplateRenderError(str(exc)) from exc
    if not subject:
        raise TemplateRenderError("Rendered subject is empty.")
    return RenderedEmail(
        to_email=recipient.email,
        subject=subject,
        body=body,
        body_format=email_template.body_format,
        from_email=settings.EMAILAUTO_DEFAULT_FROM_EMAIL,
        idempotency_key=idempotency_key,
        metadata={"campaign_id": campaign.id, "recipient_id": recipient.id},
    )

