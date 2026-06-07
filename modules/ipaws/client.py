"""
IPAWS-OPEN REST/SOAP client.

Posts CAP XML payloads to the FEMA IPAWS-OPEN gateway over mutual TLS. Auth
is delegated to :mod:`modules.ipaws.auth`.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from .auth import IPAWSCredentials, build_authenticated_session

logger = logging.getLogger(__name__)


class IPAWSClient:
    """Mutual-TLS HTTPS client for FEMA IPAWS-OPEN."""

    def __init__(self, cert_path: str, endpoint: str):
        self.cert_path = cert_path
        self.endpoint = endpoint.rstrip("/")
        self._creds = IPAWSCredentials(cert_path=cert_path)
        self._session = build_authenticated_session(self._creds)

    def ping(self) -> bool:
        """Best-effort liveness check against the configured endpoint."""
        logger.info("Pinging IPAWS at %s", self.endpoint)
        try:
            response = self._session.get(self.endpoint, timeout=5)
            return response.status_code < 500
        except requests.RequestException as exc:
            logger.debug("IPAWS ping failed: %s", exc)
            return False

    def submit_cap(self, xml_payload: str) -> dict[str, Any]:
        """Submit a CAP XML payload."""
        logger.info("Submitting CAP XML to IPAWS")
        try:
            response = self._session.post(
                f"{self.endpoint}/post",
                data=xml_payload,
                headers={"Content-Type": "application/xml"},
                timeout=10,
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {
                    "status": "ACCEPTED" if response.status_code == 200 else "ERROR",
                    "raw_response": response.text,
                    "status_code": response.status_code,
                }
        except requests.RequestException as exc:
            logger.error("IPAWS submission failed: %s", exc)
            raise
