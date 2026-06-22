# Web route test matrix

Maps each URL in `src/emailauto/web/urls.py` to at least one pytest that exercises it.
Primary coverage lives in `tests/web/test_routes.py`; supplemental tests are noted where
they add edge-case depth.

Run the route checklist:

```powershell
pytest tests/web/test_routes.py -q
```

| Route | Method | Primary test | Notes |
|-------|--------|--------------|-------|
| `/accounts/login/` | GET | `test_route_login_page_renders` | POST login flow: `test_non_staff_operator_can_log_in_and_use_dashboard` (`test_auth_and_partials.py`) |
| `/accounts/logout/` | POST | `test_route_logout_post_redirects_to_login` | |
| `/health/` | GET | `test_route_health_get_returns_json_status` | Degraded DB: `test_health_degraded_when_db_fails` (`test_web_coverage.py`) |
| `/health/?deep=1` | GET | `test_route_health_deep_get_returns_json_probe_keys` | Cache/broker failures: `test_health_deep_degraded_on_cache_failure` (`test_max_coverage_web.py`) |
| `/` | GET | `test_route_dashboard_authenticated_returns_200` | Anonymous redirect: `test_route_dashboard_anonymous_redirects_to_login` |
| `/schedules/` | GET | `test_route_schedules_authenticated_returns_200` | Enabled schedule content: `test_schedules_page_lists_enabled_schedule` (`test_views_render.py`) |
| `/runs/<run_id>/` | GET | `test_route_campaign_run_detail_existing_and_missing` | Per-run stats UI: `test_run_page_shows_per_run_stats` (`test_views_render.py`) |
| `/campaigns/<campaign_id>/` | GET | `test_route_campaign_detail_existing_and_missing` | |
| `/campaigns/<id>/trigger/` | POST | `test_route_campaign_trigger_requires_operator_permission` | Success path: `test_route_campaign_trigger_succeeds_with_operator`; creates outbox: `test_trigger_campaign_creates_outbox` (`test_operator_actions.py`) |
| `/campaigns/<id>/pause/` | POST | `test_route_campaign_pause_rejects_invalid_state` | Happy path: `test_pause_resume_cancel_campaign` (`test_operator_actions.py`) |
| `/campaigns/<id>/resume/` | POST | `test_route_campaign_resume_rejects_invalid_state` | Happy path: `test_pause_resume_cancel_campaign` (`test_operator_actions.py`) |
| `/campaigns/<id>/cancel/` | POST | `test_route_campaign_cancel_succeeds_for_cancellable_campaign` | Also covered by `test_pause_resume_cancel_campaign` |
| `/outbox/<outbox_id>/` | GET | `test_route_outbox_detail_existing_and_missing` | Action flags: `test_outbox_detail_action_flags` (`test_max_coverage_web.py`) |
| `/outbox/<id>/retry/` | POST | `test_route_outbox_retry_rejects_invalid_status` | Happy path: `test_outbox_action_paths` (`test_web_coverage.py`) |
| `/outbox/<id>/cancel/` | POST | `test_route_outbox_cancel_rejects_invalid_status` | Happy path: `test_outbox_cancel_action` (`test_operator_actions.py`) |
| `/outbox/<id>/force_requeue/` | POST | `test_route_outbox_force_requeue_rejects_invalid_status` | Happy path: `test_outbox_action_paths` (`test_web_coverage.py`) |
| `/dlq/` | GET | `test_route_dlq_list_returns_200` | |
| `/dlq/<outbox_id>/requeue/` | POST | `test_route_dlq_requeue_rejects_non_retriable_row` | Happy path: `test_requeue_dlq_action` (`test_operator_actions.py`); GET → 405: `test_requeue_dlq_rejects_get` |
| `/suppress/` | POST | `test_route_suppress_rejects_missing_email` | Success + normalization: `test_add_suppression_normalises_email` (`test_operator_actions.py`) |
| `/unsuppress/` | POST | `test_route_unsuppress_rejects_missing_email` | |
| `/subscription/` | POST | `test_route_subscription_rejects_missing_email_and_unknown_action` | Subscribe success: `test_set_subscription_paths` (`test_max_coverage_web.py`) |
| `/partials/stats/` | GET | `test_route_partials_stats_returns_200` | Bad `campaign_id`: `test_stats_partial_ignores_malformed_campaign_id` (`test_auth_and_partials.py`) |
| `/partials/outbox/` | GET | `test_route_partials_outbox_returns_200` | |
| `/partials/system/` | GET | `test_route_partials_system_returns_200` | Rate-limit panel text: `test_system_panel_reports_rate_limit_status` (`test_views_render.py`) |

Cross-cutting operator behavior (not tied to a single route):

| Concern | Test file | Test name |
|---------|-----------|-----------|
| Operator permission (403) | `test_operator_permission.py` | `test_operator_actions_require_permission` |
| Login required (302) | `test_operator_actions.py` | `test_operator_actions_require_login` |
| Open redirect blocked | `test_operator_actions.py` | `test_open_redirect_is_blocked` |
| POST rate limit | `test_max_coverage_web.py` | `test_operator_rate_limit_blocks_excess` |

See also [web_routes.md](web_routes.md) for route behavior and [cli.md](cli.md) for management commands.
