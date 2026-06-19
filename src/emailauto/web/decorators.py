from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse


def operator_required(view_func):
    """Require login plus the campaigns.operate_campaign permission (or staff)."""

    @login_required
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.user.is_staff or request.user.has_perm("campaigns.operate_campaign"):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Operator permission required.")

    return _wrapped


def operator_rate_limit(view_func):
    """Simple per-user POST rate limit for operator mutation endpoints."""

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.method == "POST" and request.user.is_authenticated:
            limit = settings.EMAILAUTO_OPERATOR_RATE_LIMIT
            if limit > 0:
                key = f"operator_rate:{request.user.pk}:{view_func.__name__}"
                cache.add(key, 0, timeout=60)
                try:
                    count = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=60)
                    count = 1
                if count > limit:
                    messages.error(request, "Too many operator actions; try again shortly.")
                    return redirect(reverse("emailauto:dashboard"))
        return view_func(request, *args, **kwargs)

    return _wrapped
