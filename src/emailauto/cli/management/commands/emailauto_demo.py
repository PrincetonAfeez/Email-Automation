from __future__ import annotations

from importlib import import_module

from django.core.management.base import BaseCommand, CommandParser

from emailauto.teaching import safe_demos

UNSAFE_DEMOS = {
    "unsafe-direct-send": "emailauto.teaching.unsafe_direct_send",
    "unsafe-no-idempotency": "emailauto.teaching.unsafe_no_idempotency",
    "unsafe-duplicate-retry": "emailauto.teaching.unsafe_retry_duplicate",
    "unsafe-double-dispatch": "emailauto.teaching.unsafe_double_dispatch",
    "unsafe-cache-truth": "emailauto.teaching.unsafe_cache_as_truth",
}


class Command(BaseCommand):
    help = "Run safe pipeline demos and unsafe teaching demos. Demos never send real email."

    def add_arguments(self, parser: CommandParser) -> None:
        names = sorted(safe_demos.SAFE_DEMOS) + ["all"] + sorted(UNSAFE_DEMOS) + ["list"]
        parser.add_argument("name", choices=names)

    def handle(self, *args, **options):
        name = options["name"]
        if name == "list":
            self.stdout.write("safe demos:")
            for demo in sorted(safe_demos.SAFE_DEMOS):
                self.stdout.write(f"  {demo}")
            self.stdout.write("  all")
            self.stdout.write("unsafe demos:")
            for demo in sorted(UNSAFE_DEMOS):
                self.stdout.write(f"  {demo}")
            return

        if name == "all":
            result = safe_demos.run_all()
        elif name in safe_demos.SAFE_DEMOS:
            result = safe_demos.SAFE_DEMOS[name]()
        else:
            module = import_module(UNSAFE_DEMOS[name])
            result = module.run_demo()

        for key, value in result.items():
            self.stdout.write(f"{key}\t{value}")
