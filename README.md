<div align="center">

# 🛰️ CAP-IPAWS Bridge

**A production-grade integration layer that ingests, validates, and routes federally authenticated Common Alerting Protocol (CAP 1.2) messages from FEMA's IPAWS-OPEN system — with automatic failover broadcasting over offline mesh networks.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![IPAWS](https://img.shields.io/badge/FEMA-IPAWS--OPEN-003366?style=for-the-badge)](https://www.fema.gov/emergency-managers/practitioners/integrated-public-alert-warning-system)
[![CAP](https://img.shields.io/badge/CAP-1.2-E64A19?style=for-the-badge)](http://docs.oasis-open.org/emergency/cap/v1.2/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue?style=for-the-badge)](LICENSE)

<br/>

> The last mile between federal emergency data and the people who need it. CAP-IPAWS Bridge authenticates against FEMA's IPAWS-OPEN API, validates incoming CAP alerts against the OASIS CAP 1.2 schema, and routes verified alerts across Telegram, SMS, push notifications, and offline LoRa mesh networks — all in real time.

[Overview](#-overview) · [Architecture](#-architecture) · [IPAWS Integration](#-ipaws-integration) · [CAP Composer](#-cap-message-composer) · [Setup](#-getting-started) · [API Docs](#-api-reference)

</div>

---

## 📌 Overview

CAP-IPAWS Bridge is **Module 4** — the federal interoperability layer — of the Rapid Alert Platform ecosystem. It solves a critical integration problem: how do you take alerts issued by the 1,500+ IPAWS-authorized emergency alerting authorities across the U.S. and route them reliably to affected populations, including those in areas where standard communication infrastructure has failed?

The bridge operates as a continuously running Python service that:

1. **Authenticates** with FEMA's IPAWS-OPEN API using signed credentials
2. **Polls** for new CAP 1.2 alerts at configurable intervals (default: 30 seconds)
3. **Validates** alert XML against the OASIS CAP 1.2 schema with geographic polygon verification
4. **Routes** verified alerts through the `rapid-alert-platform` delivery pipeline
5. **Bridges** alerts to `resilient-mesh-gateway` for offline mesh broadcast when standard delivery fails
6. **Composes** new CAP alerts via a web UI for jurisdictions that need to originate their own warnings

---

## 🔗 Ecosystem Position

```
                    ┌──────────────────────────────┐
                    │    FEMA IPAWS-OPEN API        │
                    │    (Federal Alert Source)     │
                    └──────────────┬───────────────┘
                                   │ CAP 1.2 XML + Auth
                    ┌──────────────▼───────────────┐
                    │      cap-ipaws-bridge         │ ← YOU ARE HERE
                    │                               │
                    │  • Schema validation          │
                    │  • Geographic targeting       │
                    │  • Multi-channel routing      │
                    │  • CAP message composer       │
                    └──┬──────────────────────┬────┘
                       │                      │
          ┌────────────▼──────┐   ┌───────────▼────────────┐
          │  rapid-alert-     │   │  resilient-mesh-       │
          │  platform         │   │  gateway               │
          │  (Online delivery)│   │  (Offline mesh relay)  │
          └───────────────────┘   └────────────────────────┘
```

---

## ✨ Features

| Feature | Status | Description |
|---|:---:|---|
| 🛰️ **IPAWS-OPEN Integration** | ✅ Live | Authenticated polling of FEMA's federal alert API |
| 📋 **CAP 1.2 Validation** | ✅ Live | Full OASIS schema validation + geographic polygon verification |
| 🗺️ **CAP Alert Composer** | ✅ Live | Web UI to author and publish CAP alerts with map-based zone drawing |
| 🌊 **NOAA/NWS Feed Ingest** | ✅ Live | Real-time ingestion of National Weather Service CAP feeds |
| 🔁 **Multi-Channel Routing** | ✅ Live | Routes verified alerts to Telegram, SMS, push, and mesh simultaneously |
| 📡 **Mesh Failover Bridge** | ✅ Live | Automatic handoff to `resilient-mesh-gateway` when online delivery fails |
| 🪝 **Webhook Dispatcher** | ✅ Live | Configurable webhook callbacks for third-party system integration |
| ✅ **Digital Signature Verification** | ✅ Live | Verifies IPAWS alert signatures before routing |
| 📊 **Alert Dashboard** | ✅ Live | React-based live monitoring of ingested alerts and delivery status |
| 🔄 **Deduplication Engine** | ✅ Live | Content-hash dedup prevents duplicate alert delivery across channels |
| 📝 **Full Audit Trail** | ✅ Live | Every alert ingestion, validation result, and routing decision is logged |

---

## 🏗️ Architecture

### System Components

```
cap-ipaws-bridge/
├── modules/
│   ├── ipaws/              # IPAWS-OPEN API client + authentication
│   │   ├── client.py       # SOAP/REST IPAWS-OPEN connector
│   │   ├── auth.py         # Certificate-based authentication handler
│   │   └── validator.py    # CAP 1.2 XML schema validator
│   ├── cap/                # CAP message processing
│   │   ├── parser.py       # CAP 1.2 XML → Python object mapper
│   │   ├── composer.py     # CAP alert authoring and publishing
│   │   └── geo.py          # Geographic polygon processing (PostGIS)
│   ├── routing/            # Multi-channel alert routing
│   │   ├── router.py       # Routing decision engine
│   │   ├── rapid_alert.py  # rapid-alert-platform API client
│   │   └── mesh_bridge.py  # resilient-mesh-gateway bridge client
│   ├── feeds/              # External alert source integrations
│   │   ├── noaa.py         # NOAA CAP feed parser
│   │   ├── nws.py          # National Weather Service feed client
│   │   └── usgs.py         # USGS earthquake alert feed
│   └── api/                # REST API endpoints
│       ├── alerts.py       # Alert CRUD and query endpoints
│       ├── compose.py      # CAP composer API
│       └── webhooks.py     # Outbound webhook dispatcher
├── cap_composer_module/    # CAP 1.2 alert authoring engine (Wagtail-based)
├── etc/
│   ├── eas_alert_parser.py # Emergency Alert System format parser
│   └── simulator.py        # Alert feed simulator for offline testing
├── script/                 # Utility scripts (DB admin, config merge)
├── config.template         # Full configuration reference
├── compose.yaml            # Docker Compose for full stack deployment
├── Dockerfile
└── requirements.txt
```

### Alert Processing Pipeline

```
IPAWS-OPEN API
      │
      ▼ (every 30s)
┌─────────────────┐     ┌──────────────────┐
│  IPAWS Client   │────►│  CAP Validator   │
│  (auth + poll)  │     │  (schema + sig)  │
└─────────────────┘     └────────┬─────────┘
                                  │ valid alert
                         ┌────────▼─────────┐
                         │  Dedup Engine    │
                         │  (content hash)  │
                         └────────┬─────────┘
                                  │ new alert
                    ┌─────────────▼──────────────┐
                    │      Routing Engine         │
                    │  (geo filter + channel sel) │
                    └──┬──────────┬──────────┬───┘
                       │          │          │
              ┌────────▼──┐  ┌────▼────┐  ┌─▼──────────┐
              │  Telegram  │  │  rapid- │  │  mesh-     │
              │  /SMS/Push │  │  alert  │  │  gateway   │
              └────────────┘  │  platform│  │  bridge    │
                              └──────────┘  └────────────┘
```

---

## 🛰️ IPAWS Integration

### Authentication

The bridge authenticates with IPAWS-OPEN using a **digital certificate** issued by FEMA to authorized alerting authorities. For development and testing, a sandbox certificate is provided.

```python
# modules/ipaws/auth.py
from modules.ipaws.client import IpawsClient

client = IpawsClient(
    endpoint="https://apps.fema.gov/IPAWSOPEN_EAS_SERVICE/rest",
    cert_path="/etc/ipaws/cert.p12",
    cert_password=os.environ["IPAWS_CERT_PASSWORD"],
    sandbox=os.environ.get("IPAWS_SANDBOX", "true") == "true"
)
```

### Polling Configuration

```yaml
# config.template (excerpt)
ipaws:
  poll_interval_seconds: 30
  max_alerts_per_poll: 100
  alert_types:
    - "Alert"
    - "Update"
    - "Cancel"
  geographic_filter:
    enabled: true
    states: ["CA", "OR", "WA", "NV", "AZ"]  # configurable
```

---

## 📝 CAP Message Composer

The embedded CAP Composer (adapted from the WMO Regional Association for Africa implementation) provides a **web-based UI** for emergency managers to author and publish CAP 1.2 compliant alerts:

- Draw alert zones directly on a map (polygon or radius)
- Select hazard type, severity, urgency, and certainty
- Preview the generated CAP 1.2 XML before publishing
- Validate against schema and submit to IPAWS-OPEN in one click

Access the composer at: `http://localhost:8080/composer`

---

## 🌊 External Feed Sources

| Source | Format | Update Frequency | Coverage |
|---|---|---|---|
| **NOAA Weather** | CAP 1.2 Atom | 1–2 min | National |
| **NWS Alerts** | CAP 1.2 XML | 1 min | National |
| **USGS Earthquakes** | GeoJSON → CAP | Real-time | National |
| **FEMA IPAWS-OPEN** | CAP 1.2 SOAP/REST | 30s (configurable) | National |

---

## 🚀 Getting Started

### Prerequisites

- Docker 20+ and Docker Compose
- Python 3.11+ (for local development)
- IPAWS sandbox or production certificate (`.p12` format)
- PostgreSQL 14+ with PostGIS extension

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Kadivendi/cap-ipaws-bridge.git
cd cap-ipaws-bridge

# 2. Configure environment
cp config.template config.ini
# Edit config.ini with your IPAWS credentials and channel settings

# 3. Launch with Docker Compose
docker compose up -d

# 4. Access the services
# Alert API:      http://localhost:8000/docs
# CAP Composer:   http://localhost:8080/composer
# Alert Dashboard: http://localhost:8080/dashboard
```

### Development Setup

```bash
pip install -r requirements.txt

# Run the bridge in development mode with simulated IPAWS feed
python launch.sh --sandbox --simulate-feed

# Run just the CAP composer module
cd cap_composer_module
pip install -e .
python manage.py runserver
```

---

## 📡 API Reference

All endpoints are documented at `http://localhost:8000/docs` (Swagger UI).

### Key Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/alerts` | List ingested alerts with filtering |
| `GET` | `/api/alerts/{id}` | Get alert detail + delivery status |
| `POST` | `/api/compose` | Author and publish a new CAP alert |
| `POST` | `/api/webhooks` | Register a delivery webhook |
| `GET` | `/api/feeds/status` | Real-time feed health check |
| `POST` | `/api/mesh/broadcast` | Trigger manual mesh rebroadcast for an alert |

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Test IPAWS authentication (sandbox mode)
python -m pytest tests/test_ipaws_auth.py -v

# Run CAP validation tests against sample XML files
python -m pytest tests/test_cap_validator.py -v

# Simulate full alert pipeline end-to-end
python etc/simulator.py --alerts 50 --interval 2
```

---

## 🤝 Contributing

```bash
git checkout -b feat/your-feature
git commit -m "feat(scope): description"
git push origin feat/your-feature
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 📄 License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

---

<div align="center">
  <sub>Part of the <a href="https://github.com/Kadivendi/rapid-alert-platform">Rapid Alert Platform</a> ecosystem · Connects the federal alert backbone to real people, through any available channel.</sub>
</div>
