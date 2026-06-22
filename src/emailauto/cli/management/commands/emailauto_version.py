"""Print the installed EmailAuto package version."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print the EmailAuto package version."

    def handle(self, *args, **options):
        try:
            package_version = version("email-automation-capstone")
        except PackageNotFoundError:
            package_version = "unknown"
        self.stdout.write(package_version)
