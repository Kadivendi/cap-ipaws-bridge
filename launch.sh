#!/usr/bin/env bash
# launch.sh — convenience wrapper referenced by README.md.
#
# Spins up the bridge plus the dashboard via docker compose. Pass --sandbox to
# pin IPAWS_SANDBOX=true so the IPAWS round-trip is exercised in dry-run mode
# until you provide a real .p12 in ./certs.
set -euo pipefail

SANDBOX=false
SIMULATE=false
for arg in "$@"; do
  case "$arg" in
    --sandbox)        SANDBOX=true ;;
    --simulate-feed)  SIMULATE=true ;;
    --help|-h)
      cat <<USAGE
Usage: $0 [--sandbox] [--simulate-feed]

Options:
  --sandbox         Force IPAWS_SANDBOX=true even if a cert is mounted.
  --simulate-feed   Hint the bridge to use simulated NOAA / NWS / USGS feeds.
USAGE
      exit 0
      ;;
  esac
done

export IPAWS_SANDBOX="$SANDBOX"
export USE_SIMULATED_FEEDS="$SIMULATE"

exec docker compose -f compose.yaml up "$@"
