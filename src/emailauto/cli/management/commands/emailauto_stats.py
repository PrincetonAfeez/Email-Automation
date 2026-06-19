from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser

from emailauto.cache.stats_cache import get_dashboard_stats
from emailauto.campaigns.models import Campaign


class Command(BaseCommand):
    help = "Print dashboard stats, or per-campaign stats."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action")
        sub.add_parser("dashboard")
        campaign = sub.add_parser("campaign")
        campaign.add_argument("name")
        # Backwards-compatible flag for the no-subcommand form.
        parser.add_argument("--campaign-id", type=int)

    def handle(self, *args, **options):
        action = options.get("action")
        if action == "campaign":
            try:
                campaign = Campaign.objects.get(name=options["name"])
            except Campaign.DoesNotExist as exc:
                raise CommandError(f"No campaign named '{options['name']}'.") from exc
            stats = get_dashboard_stats(campaign_id=campaign.id)
        else:
            # "dashboard" or no subcommand -> global (optionally filtered by --campaign-id).
            stats = get_dashboard_stats(campaign_id=options.get("campaign_id"))
        for key, value in stats.items():
            self.stdout.write(f"{key}\t{value}")
