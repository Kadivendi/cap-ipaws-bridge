"""
CAP composer views.

The single ``composer`` view renders a small HTML form; the
``compose_submit`` view validates the input, forwards it to the bridge's
FastAPI ``/api/v1/compose`` endpoint, and surfaces the response so the
operator can confirm the CAP XML went through to IPAWS.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


SEVERITIES = ("Extreme", "Severe", "Moderate", "Minor", "Unknown")
URGENCIES = ("Immediate", "Expected", "Future", "Past", "Unknown")
CERTAINTIES = ("Observed", "Likely", "Possible", "Unlikely", "Unknown")


@require_http_methods(["GET"])
def composer(request: HttpRequest):
    """Render the CAP composer form."""
    return render(
        request,
        "composer.html",
        {
            "severities": SEVERITIES,
            "urgencies": URGENCIES,
            "certainties": CERTAINTIES,
            "bridge_url": settings.CAP_BRIDGE_COMPOSE_URL,
        },
    )


@csrf_exempt
@require_http_methods(["POST"])
def compose_submit(request: HttpRequest):
    """Forward the composed alert to the bridge's compose endpoint."""
    try:
        if request.content_type and request.content_type.startswith("application/json"):
            payload: dict[str, Any] = json.loads(request.body or b"{}")
        else:
            payload = {
                "event_id": request.POST.get("event_id", "").strip() or None,
                "severity": request.POST.get("severity", "Severe"),
                "headline": request.POST.get("headline", ""),
                "description": request.POST.get("description", ""),
                "instruction": request.POST.get("instruction", ""),
                "target_areas": [
                    a.strip()
                    for a in request.POST.get("target_areas", "").splitlines()
                    if a.strip()
                ],
            }
    except json.JSONDecodeError as exc:
        return JsonResponse({"error": f"invalid JSON: {exc}"}, status=400)

    # Server-side enum validation mirrors modules/ipaws/validator.py so we
    # fail closed even when the operator hand-crafts a request.
    if payload.get("severity") not in SEVERITIES:
        return JsonResponse(
            {"error": f"severity must be one of {SEVERITIES}"}, status=400
        )

    try:
        response = requests.post(
            settings.CAP_BRIDGE_COMPOSE_URL,
            json=payload,
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.warning("bridge POST failed: %s", exc)
        return JsonResponse(
            {"error": "bridge unreachable", "detail": str(exc)},
            status=502,
        )

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}

    return JsonResponse(
        {"status_code": response.status_code, "bridge_response": body},
        status=response.status_code if response.status_code < 500 else 502,
    )
