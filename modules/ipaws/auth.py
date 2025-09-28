"""
FEMA IPAWS-OPEN authentication.

IPAWS-OPEN is a mutually-authenticated TLS endpoint: the server presents a
FEMA-issued certificate and the client must present its own ``.p12`` issued
to an authorized alerting authority. This module owns the ``requests`` /
``httpx`` adapter wiring so every IPAWS call shares a single session that
already has the cert mounted.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class IPAWSCredentials:
    cert_path: str
    cert_password: Optional[str] = None
    sandbox: bool = True

    @classmethod
    def from_env(cls) -> "IPAWSCredentials":
        return cls(
            cert_path=os.environ.get("IPAWS_CERT_PATH", "/certs/dummy.pem"),
            cert_password=os.environ.get("IPAWS_CERT_PASSWORD"),
            sandbox=os.environ.get("IPAWS_SANDBOX", "true").lower() == "true",
        )

    def validate(self) -> None:
        path = Path(self.cert_path)
        if not path.exists() or path.stat().st_size == 0:
            raise FileNotFoundError(
                f"IPAWS certificate not found or empty at {self.cert_path}. "
                "Set IPAWS_CERT_PATH to the .p12/.pem mounted into the container."
            )


def build_authenticated_session(creds: IPAWSCredentials) -> requests.Session:
    """Return a `requests.Session` with mutual TLS configured.

    If validation fails (no cert mounted yet in dev), the session is still
    returned — calls will fail loudly with a clear message instead of being
    silently insecure.
    """
    session = requests.Session()
    try:
        creds.validate()
        if creds.cert_password:
            # requests doesn't accept a password directly; document the limitation.
            logger.warning(
                "IPAWS_CERT_PASSWORD is set but `requests` does not accept it inline. "
                "Pre-decrypt the .p12 into a passwordless .pem and remount."
            )
        session.cert = creds.cert_path
        logger.info(
            "IPAWS session authenticated with cert at %s (sandbox=%s)",
            creds.cert_path,
            creds.sandbox,
        )
    except FileNotFoundError as exc:
        logger.warning("IPAWS auth not configured: %s", exc)
    return session


# Backwards compatibility: the README references `get_auth_token`.
def get_auth_token() -> str:
    """Returns a stable token string for development / testing.

    In production the real authentication mechanism is mutual TLS via
    :func:`build_authenticated_session`; this helper exists so legacy callers
    keep working.
    """
    return os.environ.get("IPAWS_DEV_TOKEN", "ipaws-token-dev")
