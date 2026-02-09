from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from datetime import datetime
import xml.etree.ElementTree as ET

# In-memory store for recent dispatches
recent_alerts = []

from modules.ipaws.client import IPAWSClient
from modules.api.admin import admin_router
from modules.api.webhooks import webhook_router
from modules.api.metrics import metrics_router
from modules.processing.alert_cache import AlertCache
from modules.processing.dedup_engine import DedupEngine
from modules.routing.mesh_bridge import MeshBridge
from modules.routing.circuit_breaker import CircuitBreaker
from modules.audit.audit_logger import AuditLogger
from modules.api.rate_limiter import RateLimitMiddleware

app = FastAPI(
    title="CAP-IPAWS Bridge",
    description="Bridge module translating internal Rapid Alert Platform events into CAP 1.2 and dispatching to FEMA IPAWS-OPEN.",
    version="1.0.0"
)

# Wire up orphans
app.add_middleware(RateLimitMiddleware)
app.include_router(admin_router, prefix="/admin")
app.include_router(webhook_router, prefix="/webhooks")
app.include_router(metrics_router, prefix="/metrics")

alert_cache = AlertCache()
dedup_engine = DedupEngine()
mesh_bridge = MeshBridge()
circuit_breaker = CircuitBreaker()
audit_logger = AuditLogger()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],  # Restricted in production
    allow_methods=["*"],
    allow_headers=["*"],
)

ipaws_client = IPAWSClient(
    cert_path=os.environ.get("IPAWS_CERT_PATH", "/certs/dummy.pem"),
    endpoint=os.environ.get("IPAWS_ENDPOINT", "https://tds.fema.gov/ipaws")
)

class AlertPayload(BaseModel):
    event_id: str
    severity: str
    headline: str
    description: str
    instruction: str
    target_areas: list[str]

@app.post("/api/v1/compose")
async def compose_cap(payload: AlertPayload):
    """
    Generate CAP XML from an internal alert payload and route to IPAWS.
    """
    try:
        # Generate CAP XML using ElementTree
        root = ET.Element("alert", xmlns="urn:oasis:names:tc:emergency:cap:1.2")
        ET.SubElement(root, "identifier").text = payload.event_id
        ET.SubElement(root, "sender").text = "rapid_alert_platform@kadivendi.com"
        ET.SubElement(root, "sent").text = f"{datetime.utcnow().isoformat()}Z"
        ET.SubElement(root, "status").text = "Actual"
        ET.SubElement(root, "msgType").text = "Alert"
        ET.SubElement(root, "scope").text = "Public"
        info = ET.SubElement(root, "info")
        ET.SubElement(info, "category").text = "Safety"
        ET.SubElement(info, "event").text = "Emergency Action"
        ET.SubElement(info, "urgency").text = "Immediate"
        ET.SubElement(info, "severity").text = payload.severity
        ET.SubElement(info, "certainty").text = "Observed"
        ET.SubElement(info, "headline").text = payload.headline
        ET.SubElement(info, "description").text = payload.description
        ET.SubElement(info, "instruction").text = payload.instruction
        
        cap_xml = ET.tostring(root, encoding="unicode", xml_declaration=True)
        
        try:
            response_data = ipaws_client.submit_cap(cap_xml)
            status_text = "ACCEPTED"
        except Exception as api_err:
            status_text = f"FAILED: {api_err}"
            response_data = {}
            
        recent_alerts.append({
            "event_id": payload.event_id,
            "headline": payload.headline,
            "status": status_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {"status": "success", "ipaws_response": response_data, "cap_xml": cap_xml}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "ipaws_connected": ipaws_client.ping()}

@app.get("/api/v1/alerts")
async def get_alerts():
    return {"alerts": recent_alerts}
