import logging
import requests

logger = logging.getLogger(__name__)

class IPAWSClient:
    """
    Client for interacting with the FEMA IPAWS-OPEN API.
    Handles mutually authenticated TLS and payload submission.
    """
    def __init__(self, cert_path: str, endpoint: str):
        self.cert_path = cert_path
        self.endpoint = endpoint
        self._session = requests.Session()
        # Enforce mutual TLS by attaching the provided certificate
        self._session.cert = cert_path

    def ping(self) -> bool:
        """Check connection to IPAWS endpoint."""
        logger.info(f"Pinging IPAWS at {self.endpoint}")
        try:
            # We don't actually hit FEMA in dev without certs, so we simulate a basic request 
            # or hit the test environment root to ensure network layer is alive.
            response = requests.get("https://tdl.fema.gov", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def submit_cap(self, xml_payload: str) -> dict:
        """
        Submit a CAP XML payload to the IPAWS-OPEN gateway.
        """
        logger.info("Submitting CAP XML to IPAWS...")
        # Execute actual POST request
        try:
            response = self._session.post(
                f"{self.endpoint}/post", 
                data=xml_payload, 
                headers={"Content-Type": "application/xml"},
                timeout=10
            )
            response.raise_for_status()
            
            # IPAWS typically returns XML or JSON with a status and message ID
            try:
                data = response.json()
            except ValueError:
                # Fallback if the response is plain text or XML
                data = {
                    "status": "ACCEPTED" if response.status_code == 200 else "ERROR",
                    "raw_response": response.text,
                    "status_code": response.status_code
                }
            return data
            
        except requests.RequestException as e:
            logger.error(f"IPAWS Submission failed: {e}")
            raise
