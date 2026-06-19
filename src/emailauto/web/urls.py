from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import path

from emailauto.web import views

app_name = "emailauto"

urlpatterns = [
    # Standalone operator login/logout (any active user, not only Django staff).
    path("accounts/login/", auth_views.LoginView.as_view(template_name="emailauto/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="emailauto:login"), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("schedules/", views.schedules, name="schedules"),
    path("runs/<int:run_id>/", views.campaign_run_detail, name="campaign_run_detail"),
    path("campaigns/<int:campaign_id>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<int:campaign_id>/<str:action>/", views.campaign_action, name="campaign_action"),
    path("outbox/<int:outbox_id>/", views.outbox_detail, name="outbox_detail"),
    path("outbox/<int:outbox_id>/<str:action>/", views.outbox_action, name="outbox_action"),
    path("dlq/", views.dlq, name="dlq"),
    path("dlq/<int:outbox_id>/requeue/", views.requeue_dlq, name="requeue_dlq"),
    path("suppress/", views.add_suppression, name="add_suppression"),
    path("partials/stats/", views.stats_partial, name="stats_partial"),
    path("partials/outbox/", views.outbox_table_partial, name="outbox_table_partial"),
    path("partials/system/", views.system_partial, name="system_partial"),
]
