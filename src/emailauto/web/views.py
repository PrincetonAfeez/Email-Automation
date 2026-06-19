from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from emailauto.cache.stats_cache import get_dashboard_stats
from emailauto.campaigns.models import Campaign
from emailauto.campaigns.services import cancel_campaign, pause_campaign, resume_campaign, trigger_campaign_now
from emailauto.core.states import CampaignStatus, OutboxStatus
from emailauto.observability.stats import recent_failures, recent_send_throughput, run_counts
from emailauto.outbox.models import EmailOutbox
from emailauto.outbox.services import cancel_outbox, force_requeue_outbox, requeue_outbox, retry_outbox
from emailauto.recipients.suppression import suppress_email
from emailauto.scheduling.models import CampaignRun, CampaignSchedule
from emailauto.web.decorators import operator_rate_limit, operator_required
from emailauto.workers.throttling import throttle_status


def _campaign_actions(campaign: Campaign) -> dict[str, bool]:
    return {
        "can_trigger": campaign.status in CampaignStatus.TRIGGERABLE,
        "can_pause": campaign.status in CampaignStatus.PAUSABLE,
        "can_resume": campaign.status == CampaignStatus.PAUSED,
        "can_cancel": campaign.status in CampaignStatus.CANCELLABLE,
    }


def _recent_outbox(limit: int = 100):
    return EmailOutbox.objects.select_related("campaign", "recipient").order_by("-updated_at")[:limit]


def _safe_redirect(request: HttpRequest, fallback: str) -> HttpResponse:
    target = request.POST.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect(reverse(fallback))


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    campaigns = Campaign.objects.order_by("name")[:25]
    return render(
        request,
        "emailauto/dashboard.html",
        {
            "stats": get_dashboard_stats(),
            "campaign_rows": [{"campaign": c, "actions": _campaign_actions(c)} for c in campaigns],
            "recent_failures": recent_failures(),
            "recent_outbox": _recent_outbox(),
            "throughput": recent_send_throughput(),
            "throttle": throttle_status(),
            "can_operate": request.user.is_staff or request.user.has_perm("campaigns.operate_campaign"),
        },
    )


@login_required
def schedules(request: HttpRequest) -> HttpResponse:
    upcoming = (
        CampaignSchedule.objects.select_related("campaign")
        .filter(enabled=True)
        .order_by("next_run_at", "id")[:100]
    )
    return render(
        request,
        "emailauto/schedules.html",
        {"schedules": upcoming, "scheduling_note": "All dispatch times are evaluated in UTC. The timezone column is display-only."},
    )


@login_required
def campaign_run_detail(request: HttpRequest, run_id: int) -> HttpResponse:
    run = get_object_or_404(CampaignRun.objects.select_related("campaign", "schedule"), pk=run_id)
    return render(
        request,
        "emailauto/campaign_run_detail.html",
        {
            "run": run,
            "stats": run_counts(campaign_run_id=run.id),
            "outbox_rows": run.outbox_rows.select_related("recipient").order_by("-updated_at")[:100],
        },
    )


@login_required
def campaign_detail(request: HttpRequest, campaign_id: int) -> HttpResponse:
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    return render(
        request,
        "emailauto/campaign_detail.html",
        {
            "campaign": campaign,
            "actions": _campaign_actions(campaign),
            "stats": get_dashboard_stats(campaign_id=campaign.id),
            "outbox_rows": campaign.outbox_rows.select_related("recipient").order_by("-updated_at")[:100],
            "runs": campaign.runs.order_by("-scheduled_for")[:25],
            "can_operate": request.user.is_staff or request.user.has_perm("campaigns.operate_campaign"),
        },
    )


_RETRYABLE_STATUSES = {
    OutboxStatus.PENDING,
    OutboxStatus.ENQUEUED,
    OutboxStatus.RETRY_SCHEDULED,
    OutboxStatus.REQUEUED,
    OutboxStatus.FAILED,
    OutboxStatus.DEAD_LETTERED,
}
_CANCELLABLE_STATUSES = {
    OutboxStatus.PENDING,
    OutboxStatus.ENQUEUED,
    OutboxStatus.RETRY_SCHEDULED,
    OutboxStatus.REQUEUED,
}
_FORCE_REQUEUE_STATUSES = {OutboxStatus.CLAIMED, OutboxStatus.SENDING}


@login_required
def outbox_detail(request: HttpRequest, outbox_id: int) -> HttpResponse:
    row = get_object_or_404(
        EmailOutbox.objects.select_related("campaign", "campaign_run", "recipient", "template").prefetch_related("attempts", "event_logs"),
        pk=outbox_id,
    )
    can_operate = request.user.is_staff or request.user.has_perm("campaigns.operate_campaign")
    return render(
        request,
        "emailauto/outbox_detail.html",
        {
            "row": row,
            "can_retry": can_operate and row.status in _RETRYABLE_STATUSES,
            "can_cancel": can_operate and row.status in _CANCELLABLE_STATUSES,
            "can_force_requeue": can_operate and row.status in _FORCE_REQUEUE_STATUSES,
        },
    )


@login_required
def dlq(request: HttpRequest) -> HttpResponse:
    queryset = EmailOutbox.objects.select_related("campaign", "recipient").filter(status=OutboxStatus.DEAD_LETTERED).order_by("-dead_lettered_at")
    page = Paginator(queryset, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "emailauto/dlq.html",
        {"page": page, "rows": page.object_list, "can_operate": request.user.is_staff or request.user.has_perm("campaigns.operate_campaign")},
    )


@operator_required
@operator_rate_limit
@require_POST
def requeue_dlq(request: HttpRequest, outbox_id: int) -> HttpResponse:
    try:
        requeue_outbox(outbox_id)
    except (EmailOutbox.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Requeued outbox row {outbox_id}.")
    return _safe_redirect(request, "emailauto:dlq")


@operator_required
@operator_rate_limit
@require_POST
def campaign_action(request: HttpRequest, campaign_id: int, action: str) -> HttpResponse:
    handlers = {
        "pause": pause_campaign,
        "resume": resume_campaign,
        "cancel": cancel_campaign,
    }
    try:
        if action == "trigger":
            result = trigger_campaign_now(campaign_id)
            messages.success(request, f"Triggered campaign {campaign_id}: {result.outbox_created} queued, {result.outbox_enqueued} enqueued.")
        elif action in handlers:
            campaign = handlers[action](campaign_id)
            messages.success(request, f"Campaign {campaign.name} -> {campaign.status}.")
        else:
            messages.error(request, f"Unknown campaign action: {action}.")
    except (Campaign.DoesNotExist, ValueError, RuntimeError) as exc:
        messages.error(request, str(exc))
    return _safe_redirect(request, "emailauto:dashboard")


@operator_required
@operator_rate_limit
@require_POST
def outbox_action(request: HttpRequest, outbox_id: int, action: str) -> HttpResponse:
    try:
        if action == "retry":
            row = retry_outbox(outbox_id)
            messages.success(request, f"Retry queued for outbox {outbox_id} ({row.status}).")
        elif action == "cancel":
            row = cancel_outbox(outbox_id)
            messages.success(request, f"Cancelled outbox {outbox_id} ({row.status}).")
        elif action == "force_requeue":
            row = force_requeue_outbox(outbox_id)
            messages.success(request, f"Force-requeued outbox {outbox_id} ({row.status}).")
        else:
            messages.error(request, f"Unknown outbox action: {action}.")
    except (EmailOutbox.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("emailauto:outbox_detail", outbox_id=outbox_id)


@operator_required
@operator_rate_limit
@require_POST
def add_suppression(request: HttpRequest) -> HttpResponse:
    email = (request.POST.get("email") or "").strip()
    reason = (request.POST.get("reason") or "operator").strip()
    if not email:
        messages.error(request, "An email address is required to suppress.")
    else:
        entry = suppress_email(email, reason=reason)
        messages.success(request, f"Suppressed {entry.email}.")
    return _safe_redirect(request, "emailauto:dashboard")


@login_required
def stats_partial(request: HttpRequest) -> HttpResponse:
    raw_campaign_id = request.GET.get("campaign_id")
    try:
        campaign_id = int(raw_campaign_id) if raw_campaign_id else None
    except (TypeError, ValueError):
        campaign_id = None
    stats = get_dashboard_stats(campaign_id=campaign_id)
    return render(request, "emailauto/partials/campaign_stats.html", {"stats": stats})


@login_required
def outbox_table_partial(request: HttpRequest) -> HttpResponse:
    return render(request, "emailauto/partials/outbox_table.html", {"outbox_rows": _recent_outbox()})


@login_required
def system_partial(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "emailauto/partials/system_status.html",
        {"throughput": recent_send_throughput(), "throttle": throttle_status()},
    )
