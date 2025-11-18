"""``cap-composer`` console-script entry point.

Re-exports Django's ``manage.py`` machinery so ``cap-composer runserver``
works exactly like ``python manage.py runserver`` once the package is
installed.
"""
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> None:
    """Run a Django management command."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cap_composer_app.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django is required. Install with `pip install cap-composer`."
        ) from exc
    execute_from_command_line(["cap-composer", *(argv or sys.argv[1:])])
