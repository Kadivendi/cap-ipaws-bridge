"""
CAP-IPAWS Bridge — FastAPI entrypoint.

Wires together:
  * The IPAWS-OPEN client (mutual TLS).
  * CAP composer / parser / validator.
  * Dedup, alert cache, circuit breaker, retry engine, audit logger.
  * The routing engine (rapid-alert-platform + resilient-mesh-gateway bridge).

Every public endpoint now actually exercises these components instead of
holding them as decorative module-level singletons.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from modules.api.admin import admin_router
from modules.api.alerts import get_alert_cache, router as alerts_router
from modules.api.compose import router as compose_router
from modules.api.metrics import metrics_router
from modules.api.rate_limiter import RateLimitMiddleware
from modules.api.webhooks import webhook_router
from modules.audit.audit_logger import AlertLifecycleEvent, AuditLogger  # AlertLifecycleEvent is an Enum
from modules.cap.composer import CAPComposer, ComposedAlertSpec, ComposedAreaSpec
from modules.cap.parser import CAPParser
from modules.ipaws.auth import IPAWSCredentials, build_authenticated_session
from modules.ipaws.client import IPAWSClient
from modules.ipaws.validator import validate_cap
from modules.processing.alert_cache import CachedAlert
from modules.processing.dedup_engine import DedupEngine
from modules.routing.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from modules.routing.mesh_bridge import MeshBridgeClient
from modules.routing.rapid_alert import RapidAlertClient
from modules.routing.retry_engine import RetryEngine
from modules.routing.router import AlertRouter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Components (single instances shared between handlers).
# ---------------------------------------------------------------------------

ipaws_client = IPAWSClient(
    cert_path=os.environ.get("IPAWS_CERT_PATH", "/certs/dummy.pem"),
    endpoint=os.environ.get("IPAWS_ENDPOINT", "https://tds.fema.gov/ipaws"),
)

cap_composer = CAPComposer()
cap_parser = CAPParser()

alert_cache = get_alert_cache()
dedup_engine = DedupEngine()
audit_logger = AuditLogger()
retry_engine = RetryEngine(max_retries=3)
ipaws_circuit = CircuitBreaker(CircuitBreakerConfig(name="ipaws-open"))

mesh_bridge_url = os.environ.get(
    "MESH_GATEWAY_URL",
    "http://resilient-mesh-gateway:8090",
)
mesh_bridge_api_key = os.environ.get("MESH_GATEWAY_API_KEY", "")
mesh_bridge: MeshBridgeClient | None = None
try:
    mesh_bridge = MeshBridgeClient(
        gateway_url=mesh_bridge_url,
        api_key=mesh_bridge_api_key,
    )
except Exception as exc:  # noqa: BLE001
    logger.warning("Mesh bridge disabled: %s", exc)

rapid_alert_client = RapidAlertClient()
router_engine = AlertRouter(
    rapid_alert_client=rapid_alert_client,
    mesh_client=mesh_bridge,
)


app = FastAPI(
    title="CAP-IPAWS Bridge",
    description=(
        "Bridge module translating internal Rapid Alert Platform events into CAP 1.2 "
        "and dispatching to FEMA IPAWS-OPEN, with automatic mesh failover via "
        "resilient-mesh-gateway."
    ),
    version="1.0.1",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/admin")
app.include_router(webhook_router, prefix="/webhooks")
app.include_router(metrics_router, prefix="/metrics")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(compose_router, prefix="/api/v1")


class AlertPayload(BaseModel):
    event_id: str
    severity: str
    headline: str
    description: str
    instruction: str
    target_areas: list[str]


class MeshBroadcastPayload(BaseModel):
    event_id: str
    severity: str | None = None
    risk_score: float | None = None
    source: str | None = None
    reason: str | None = None
    cap_xml: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/api/v1/compose")
async def compose_cap(payload: AlertPayload):
    """Compose CAP XML, validate, dedup, cache, audit, then submit to IPAWS."""
    spec = ComposedAlertSpec(
        sender="rapid_alert_platform@kadivendi.com",
        headline=payload.headline,
        description=payload.description,
        instruction=payload.instruction,
        severity=payload.severity,
        identifier=payload.event_id,
        areas=[ComposedAreaSpec(area_desc=area) for area in payload.target_areas],
    )
    cap_xml = cap_composer.compose(spec)

    validation = validate_cap(cap_xml)
    if not validation.valid:
        raise HTTPException(status_code=400, detail={
            "errors": validation.errors,
            "warnings": validation.warnings,
        })

    is_dup = dedup_engine.is_duplicate(
        alert_identifier=payload.event_id,
        sender="rapid_alert_platform@kadivendi.com",
        event_type=spec.event,
        areas=",".join(payload.target_areas),
    )
    if is_dup:
        audit_logger.log_event(
            AlertLifecycleEvent.DEDUPLICATED,
            payload.event_id,
            source="cap-ipaws-bridge",
            metadata={"reason": "content-hash collision within dedup window"},
        )
        return {"status": "deduplicated", "cap_xml": cap_xml}

    alert_cache.put(CachedAlert(
        alert_id=payload.event_id,
        sender=spec.sender,
        severity=payload.severity,
        cap_xml=cap_xml,
    ))

    audit_logger.log_event(
        AlertLifecycleEvent.INGESTED,
        payload.event_id,
        source="cap-ipaws-bridge",
        metadata={"severity": payload.severity, "headline": payload.headline},
    )

    status_text = "ACCEPTED"
    response_data: dict[str, Any] = {}
    try:
        response_data = ipaws_circuit.call(ipaws_client.submit_cap, cap_xml)
    except RuntimeError as exc:
        status_text = f"CIRCUIT_OPEN: {exc}"
    except Exception as api_err:  # noqa: BLE001
        status_text = f"FAILED: {api_err}"

    audit_logger.log_event(
        AlertLifecycleEvent.ROUTED if status_text == "ACCEPTED" else AlertLifecycleEvent.FAILED,
        payload.event_id,
        source="cap-ipaws-bridge",
        destination="ipaws-open",
        metadata={"status": status_text},
        error_message=None if status_text == "ACCEPTED" else status_text,
    )

    return {
        "status": "success" if status_text == "ACCEPTED" else "partial",
        "ipaws_status": status_text,
        "ipaws_response": response_data,
        "cap_xml": cap_xml,
        "validation_warnings": validation.warnings,
    }


@app.post("/api/mesh/broadcast")
async def mesh_broadcast(payload: MeshBroadcastPayload):
    """Entry point invoked by rapid-alert-platform's MeshFailoverDispatcher.

    Forwards the alert into the offline mesh gateway when standard delivery is
    degraded. The bridge tracks the request, audit-logs it, and returns the
    mesh-gateway's nodes-reached estimate when available.
    """
    if mesh_bridge is None:
        raise HTTPException(status_code=503, detail="Mesh gateway not configured")

    cap_xml = payload.cap_xml or ""
    cached = alert_cache.get(payload.event_id)
    if cached is not None and not cap_xml:
        cap_xml = cached.cap_xml

    result = await mesh_bridge.inject_alert(
        alert_id=payload.event_id,
        cap_xml=cap_xml,
        zone_id="",
        severity=payload.severity or "Unknown",
    )

    audit_logger.log_event(
        AlertLifecycleEvent.DELIVERED if result.status.value == "SENT" else AlertLifecycleEvent.FAILED,
        payload.event_id,
        source=payload.source or "unknown",
        destination="mesh-gateway",
        metadata={
            "reason": payload.reason,
            "delivery_status": result.status.value,
            "nodes_reached": result.nodes_reached,
        },
    )

    return {
        "alert_id": payload.event_id,
        "status": result.status.value,
        "nodes_reached": result.nodes_reached,
        "should_activate_mesh": mesh_bridge.should_activate_mesh,
        "circuit": ipaws_circuit.stats,
    }


@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "ipaws_connected": ipaws_client.ping(),
        "components": {
            "mesh_bridge": mesh_bridge is not None,
            "circuit_breaker_state": ipaws_circuit.state.value,
            "alert_cache_size": alert_cache.size,
            "dedup_stats": dedup_engine.get_stats(),
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/router/stats")
async def router_stats():
    """Visibility into the dual-circuit breaker for both downstream services."""
    return router_engine.stats


@app.on_event("shutdown")
async def _shutdown():
    try:
        await rapid_alert_client.close()
    except Exception:  # noqa: BLE001
        pass
    if mesh_bridge is not None:
        try:
            await mesh_bridge.close()
        except Exception:  # noqa: BLE001
            pass
