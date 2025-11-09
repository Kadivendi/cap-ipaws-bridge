"""URL config for the composer app."""
from __future__ import annotations

from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path("", views.composer, name="composer-root"),
    path("composer/", views.composer, name="composer"),
    path("compose/", views.compose_submit, name="compose-submit"),
    path("admin/", admin.site.urls),
]
