#!/usr/bin/env python
"""Django management entry point for the email automation capstone."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    # Support the src/ layout without requiring an editable install.
    src_dir = Path(__file__).resolve().parent / "src"
    if src_dir.is_dir() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emailauto.config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

