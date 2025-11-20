#!/usr/bin/env bash
# Boot the cap-ipaws-bridge backend locally.
#
# Usage:
#   script/start.sh [--reload] [--sandbox]
#
# The IPAWS-OPEN endpoint requires a client certificate; when running locally
# without one, set IPAWS_SANDBOX=true so the bridge logs (instead of fails) on
# the IPAWS round-trip.
set -euo pipefail

cd "$(dirname "$0")/.."

RELOAD_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --reload)  RELOAD_FLAG="--reload" ;;
    --sandbox) export IPAWS_SANDBOX=true ;;
  esac
done

: "${IPAWS_CERT_PATH:=/certs/dummy.pem}"
: "${IPAWS_ENDPOINT:=https://apps.fema.gov/IPAWSOPEN_EAS_SERVICE/rest}"
: "${MESH_GATEWAY_URL:=http://localhost:8090}"
: "${RAPID_ALERT_URL:=http://localhost:8080}"

export IPAWS_CERT_PATH IPAWS_ENDPOINT MESH_GATEWAY_URL RAPID_ALERT_URL

exec uvicorn src.main:app --host 0.0.0.0 --port 8000 ${RELOAD_FLAG}
