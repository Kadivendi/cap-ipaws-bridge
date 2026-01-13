#!/usr/bin/env python3
"""
Emergency Alert System (EAS) header parser.

The EAS protocol used by US broadcast television and radio prefixes every
alert audio segment with a SAME (Specific Area Message Encoding) header of
the form::

    ZCZC-ORG-EEE-PSSCCC-PSSCCC+TTTT-JJJHHMM-CCCCCCCC-

This module turns those headers into the same structured dict shape used by
the rest of the bridge (the CAP composer / IPAWS validator) so legacy EAS
captures can be replayed through the same dedup / routing / mesh-bridge
pipeline as fresh IPAWS alerts.

Example::

    >>> from etc.eas_alert_parser import parse_same_header
    >>> r = parse_same_header("ZCZC-WXR-TOR-039173+0030-1421900-KEAX/NWS-")
    >>> r["event"]
    'Tornado Warning'
    >>> r["originator"]
    'NWS'
    >>> r["areas"][0]["state_fips"]
    '39'
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)

# https://www.weather.gov/nwr/eventcodes — partial mapping covering the
# events we routinely see in the IPAWS feed. Unknown codes are surfaced
# verbatim so the caller can decide whether to drop or pass through.
EVENT_CODES: dict[str, str] = {
    "TOR": "Tornado Warning",
    "SVR": "Severe Thunderstorm Warning",
    "FFW": "Flash Flood Warning",
    "FLW": "Flood Warning",
    "TSW": "Tsunami Warning",
    "EQW": "Earthquake Warning",
    "FRW": "Fire Warning",
    "BZW": "Blizzard Warning",
    "WSW": "Winter Storm Warning",
    "HUW": "Hurricane Warning",
    "TRW": "Tropical Storm Warning",
    "CDW": "Civil Danger Warning",
    "CEM": "Civil Emergency Message",
    "EAN": "Emergency Action Notification",
    "EVI": "Evacuation Immediate",
    "HMW": "Hazardous Materials Warning",
    "LEW": "Law Enforcement Warning",
    "NUW": "Nuclear Power Plant Warning",
    "RHW": "Radiological Hazard Warning",
    "SPW": "Shelter in Place Warning",
    "TOA": "Tornado Watch",
    "SVA": "Severe Thunderstorm Watch",
    "RWT": "Required Weekly Test",
    "RMT": "Required Monthly Test",
    "DMO": "Practice / Demo Warning",
}

ORIGINATOR_CODES: dict[str, str] = {
    "PEP": "Primary Entry Point",
    "CIV": "Civil Authorities",
    "WXR": "National Weather Service",
    "EAS": "Emergency Alert System",
    "EAN": "Emergency Action Notification Network",
}


@dataclass
class EasArea:
    raw: str
    subdivision: str
    state_fips: str
    county_fips: str

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "subdivision": self.subdivision,
            "state_fips": self.state_fips,
            "county_fips": self.county_fips,
        }


@dataclass
class EasHeader:
    originator: str
    originator_name: str
    event_code: str
    event: str
    areas: list[EasArea] = field(default_factory=list)
    duration: str = ""
    issue_julian: str = ""
    issue_hhmm: str = ""
    station: str = ""

    def to_dict(self) -> dict:
        return {
            "originator": self.originator,
            "originator_name": self.originator_name,
            "event_code": self.event_code,
            "event": self.event,
            "areas": [a.to_dict() for a in self.areas],
            "duration": self.duration,
            "issue_julian": self.issue_julian,
            "issue_hhmm": self.issue_hhmm,
            "station": self.station,
        }


def _parse_area(raw: str) -> EasArea:
    # PSSCCC: 1-char subdivision, 2-char state FIPS, 3-char county FIPS.
    if len(raw) != 6:
        raise ValueError(f"area block must be 6 chars, got {raw!r}")
    return EasArea(
        raw=raw,
        subdivision=raw[0],
        state_fips=raw[1:3],
        county_fips=raw[3:6],
    )


def parse_same_header(header: str) -> dict:
    """Parse a single SAME header line and return its structured dict form."""
    if not header:
        raise ValueError("empty header")

    cleaned = header.strip().rstrip("-")
    if not cleaned.startswith("ZCZC-"):
        raise ValueError(f"missing ZCZC- prefix: {header!r}")
    parts = cleaned.split("-")
    # Expected layout (post-strip):
    #   ['ZCZC', ORG, EEE, 'PSSCCC+TTTT', 'JJJHHMM', 'CCCCCCCC']
    # The PSSCCC chunk may repeat for multi-county alerts:
    #   ['ZCZC', ORG, EEE, 'PSSCCC', 'PSSCCC+TTTT', 'JJJHHMM', 'CCCCCCCC']
    if len(parts) < 6:
        raise ValueError(f"too few fields in header: {header!r}")

    originator = parts[1]
    event_code = parts[2]
    station = parts[-1].split("/")[0]
    issue = parts[-2]
    area_tokens = parts[3:-2]
    if not area_tokens:
        raise ValueError(f"no area tokens in header: {header!r}")

    # The last area token contains the +TTTT duration suffix.
    last = area_tokens[-1]
    if "+" not in last:
        raise ValueError(f"missing duration marker (+TTTT): {header!r}")
    last_area_raw, duration = last.split("+", 1)
    area_tokens[-1] = last_area_raw

    areas: list[EasArea] = []
    for token in area_tokens:
        try:
            areas.append(_parse_area(token))
        except ValueError as exc:
            logger.warning("skipping malformed area token %r: %s", token, exc)

    issue_julian, issue_hhmm = issue[:3], issue[3:7] if len(issue) >= 7 else ""
    header_obj = EasHeader(
        originator=originator,
        originator_name=ORIGINATOR_CODES.get(originator, originator),
        event_code=event_code,
        event=EVENT_CODES.get(event_code, event_code),
        areas=areas,
        duration=duration,
        issue_julian=issue_julian,
        issue_hhmm=issue_hhmm,
        station=station,
    )
    return header_obj.to_dict()


def parse_file(path: str) -> list[dict]:
    """Parse every non-blank line of *path* as a SAME header."""
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(parse_same_header(line))
            except ValueError as exc:
                logger.warning("line %d: %s", line_no, exc)
    return out


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="etc/eas_alert_parser.py",
        description="Decode SAME / EAS headers into structured records.",
    )
    p.add_argument("header", nargs="?", help="A single SAME header to decode.")
    p.add_argument("--file", help="Decode every header (one per line) in this file.")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    if not args.header and not args.file:
        print("error: provide a header argument or --file", file=sys.stderr)
        return 2

    import json as _json

    if args.file:
        records = parse_file(args.file)
        print(_json.dumps(records, indent=2))
    else:
        record = parse_same_header(args.header)
        print(_json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
