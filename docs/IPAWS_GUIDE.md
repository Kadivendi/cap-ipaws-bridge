# IPAWS Integration Guide

## Overview

The CAP-IPAWS Bridge connects to the IPAWS-OPEN platform to receive and
disseminate Common Alerting Protocol (CAP 1.2) alerts through the federal
Integrated Public Alert and Warning System.

## Authentication

IPAWS-OPEN uses certificate-based authentication:

1. **Obtain FEMA IPAWS credentials** via the [COG registration process](https://www.fema.gov/ipaws)
2. **Install the certificate** in the bridge configuration
3. **Configure polling** endpoint in `config.yaml`

```yaml
ipaws:
  endpoint: "https://apps.fema.gov/IPAWSOPEN_EAS_SERVICE/rest/public"
  poll_interval_seconds: 30
  certificate_path: "/etc/ipaws/cert.pem"
  key_path: "/etc/ipaws/key.pem"
```

## Alert Flow

```
IPAWS-OPEN → Poll → Validate CAP 1.2 → Dedup → Route → Platform/Mesh
```

1. **Poll**: Fetch new alerts from IPAWS-OPEN REST API
2. **Validate**: Verify CAP 1.2 schema compliance
3. **Dedup**: Content-hash check against recent alerts
4. **Enrich**: Add population estimates and risk scores
5. **Route**: Dispatch to rapid-alert-platform via Kafka or mesh gateway
