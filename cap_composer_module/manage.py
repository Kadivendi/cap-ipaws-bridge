#!/usr/bin/env python3
"""Standard Django ``manage.py`` for the embedded CAP composer."""
from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cap_composer_app.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and available on "
            "your PYTHONPATH? Did you run `pip install -e .` in cap_composer_module?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
