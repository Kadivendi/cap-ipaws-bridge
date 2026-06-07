"""
CAP composer REST API.

Wraps :class:`modules.cap.composer.CAPComposer` for the web UI so
authorized emergency managers can author and publish CAP 1.2 alerts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..cap.composer import CAPComposer, ComposedAlertSpec, ComposedAreaSpec
from ..ipaws.validator import validate_cap

router = APIRouter(prefix="/compose", tags=["compose"])

_composer = CAPComposer()


class AreaPayload(BaseModel):
    area_desc: str
    polygon: list[tuple[float, float]] = Field(default_factory=list)
    circle: str | None = None
    geocode: dict[str, str] = Field(default_factory=dict)


class ComposePayload(BaseModel):
    sender: str
    headline: str
    description: str
    instruction: str
    severity: str = "Severe"
    urgency: str = "Immediate"
    certainty: str = "Observed"
    category: str = "Safety"
    event: str = "Emergency Action"
    status: str = "Actual"
    msg_type: str = "Alert"
    scope: str = "Public"
    identifier: str | None = None
    sent: datetime | None = None
    areas: list[AreaPayload] = Field(default_factory=list)


@router.post("/preview")
def preview(payload: ComposePayload) -> dict[str, Any]:
    """Compose CAP XML and return it with validation results — no IPAWS submit."""
    xml = _composer.compose(_to_spec(payload))
    result = validate_cap(xml)
    return {"cap_xml": xml, "valid": result.valid,
            "errors": result.errors, "warnings": result.warnings}


@router.post("")
def submit(payload: ComposePayload) -> dict[str, Any]:
    """Compose, validate, and (in production) hand off to the IPAWS client."""
    xml = _composer.compose(_to_spec(payload))
    result = validate_cap(xml)
    if not result.valid:
        raise HTTPException(status_code=400, detail={
            "errors": result.errors, "warnings": result.warnings,
        })
    return {"cap_xml": xml, "ready_for_ipaws": True,
            "warnings": result.warnings}


def _to_spec(payload: ComposePayload) -> ComposedAlertSpec:
    return ComposedAlertSpec(
        sender=payload.sender,
        headline=payload.headline,
        description=payload.description,
        instruction=payload.instruction,
        severity=payload.severity,
        urgency=payload.urgency,
        certainty=payload.certainty,
        category=payload.category,
        event=payload.event,
        status=payload.status,
        msg_type=payload.msg_type,
        scope=payload.scope,
        identifier=payload.identifier,
        sent=payload.sent,
        areas=[
            ComposedAreaSpec(
                area_desc=a.area_desc,
                polygon=a.polygon,
                circle=a.circle,
                geocode=a.geocode,
            )
            for a in payload.areas
        ],
    )
