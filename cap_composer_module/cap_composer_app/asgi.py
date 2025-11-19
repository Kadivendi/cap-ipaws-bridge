"""ASGI config for the composer app."""
from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cap_composer_app.settings")

application = get_asgi_application()
