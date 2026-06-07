"""
CAP 1.2 → Python object mapper.

Parses incoming CAP XML (from IPAWS-OPEN polls, NOAA, NWS) into a structured
:class:`CAPAlert` dataclass that downstream modules — dedup, routing,
mesh-bridge — can work with without re-parsing XML on every step.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from lxml import etree

logger = logging.getLogger(__name__)

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
ATOM_NS = "http://www.w3.org/2005/Atom"
NS = {"cap": CAP_NS, "atom": ATOM_NS}


@dataclass
class CAPArea:
    area_desc: str = ""
    polygon: list[tuple[float, float]] = field(default_factory=list)
    circle: str | None = None
    geocode: dict[str, str] = field(default_factory=dict)


@dataclass
class CAPInfo:
    language: str = "en-US"
    category: str = ""
    event: str = ""
    urgency: str = ""
    severity: str = ""
    certainty: str = ""
    headline: str = ""
    description: str = ""
    instruction: str = ""
    areas: list[CAPArea] = field(default_factory=list)


@dataclass
class CAPAlert:
    identifier: str
    sender: str
    sent: datetime
    status: str
    msg_type: str
    scope: str
    source: str | None
    infos: list[CAPInfo]
    raw_xml: str

    @property
    def headline(self) -> str:
        return self.infos[0].headline if self.infos else ""

    @property
    def severity(self) -> str:
        return self.infos[0].severity if self.infos else ""

    @property
    def event_type(self) -> str:
        return self.infos[0].event if self.infos else ""


class CAPParser:
    """Streaming CAP 1.2 parser tolerant of malformed feeds.

    Use :meth:`parse_single` for a one-off CAP XML document, or
    :meth:`parse_atom_feed` for an Atom-wrapped feed that contains many
    embedded CAP entries (the NOAA / NWS format).
    """

    def parse_single(self, xml_text: str | bytes) -> CAPAlert | None:
        try:
            root = etree.fromstring(
                xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text
            )
            return self._parse_alert(root, raw=etree.tostring(root, encoding="unicode"))
        except etree.XMLSyntaxError as e:
            logger.warning("CAP XML parse failed: %s", e)
            return None

    def parse_atom_feed(self, xml_text: str | bytes) -> Iterable[CAPAlert]:
        try:
            root = etree.fromstring(
                xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text
            )
        except etree.XMLSyntaxError as e:
            logger.warning("Atom feed parse failed: %s", e)
            return []

        out: list[CAPAlert] = []
        for entry in root.iterfind(f"{{{ATOM_NS}}}entry"):
            inline = entry.find(f"{{{CAP_NS}}}alert")
            if inline is not None:
                alert = self._parse_alert(inline, raw=etree.tostring(inline, encoding="unicode"))
                if alert:
                    out.append(alert)
        return out

    def _parse_alert(self, root, raw: str) -> CAPAlert | None:
        if root is None:
            return None
        try:
            ident = self._txt(root, "cap:identifier") or ""
            sender = self._txt(root, "cap:sender") or ""
            sent_text = self._txt(root, "cap:sent") or ""
            try:
                sent = datetime.fromisoformat(sent_text.replace("Z", "+00:00"))
            except ValueError:
                sent = datetime.utcnow()

            status = self._txt(root, "cap:status") or "Actual"
            msg_type = self._txt(root, "cap:msgType") or "Alert"
            scope = self._txt(root, "cap:scope") or "Public"
            source = self._txt(root, "cap:source")

            infos = [self._parse_info(info) for info in root.iterfind(f"{{{CAP_NS}}}info")]

            return CAPAlert(
                identifier=ident,
                sender=sender,
                sent=sent,
                status=status,
                msg_type=msg_type,
                scope=scope,
                source=source,
                infos=infos,
                raw_xml=raw,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse CAP alert: %s", exc)
            return None

    def _parse_info(self, info) -> CAPInfo:
        return CAPInfo(
            language=self._txt(info, "cap:language") or "en-US",
            category=self._txt(info, "cap:category") or "",
            event=self._txt(info, "cap:event") or "",
            urgency=self._txt(info, "cap:urgency") or "",
            severity=self._txt(info, "cap:severity") or "",
            certainty=self._txt(info, "cap:certainty") or "",
            headline=self._txt(info, "cap:headline") or "",
            description=self._txt(info, "cap:description") or "",
            instruction=self._txt(info, "cap:instruction") or "",
            areas=[self._parse_area(a) for a in info.iterfind(f"{{{CAP_NS}}}area")],
        )

    def _parse_area(self, area) -> CAPArea:
        polygon_text = self._txt(area, "cap:polygon") or ""
        polygon: list[tuple[float, float]] = []
        for pair in polygon_text.split():
            try:
                lat_str, lon_str = pair.split(",")
                polygon.append((float(lat_str), float(lon_str)))
            except ValueError:
                continue

        geocode: dict[str, str] = {}
        for g in area.iterfind(f"{{{CAP_NS}}}geocode"):
            name = self._txt(g, "cap:valueName") or ""
            value = self._txt(g, "cap:value") or ""
            if name:
                geocode[name] = value

        return CAPArea(
            area_desc=self._txt(area, "cap:areaDesc") or "",
            polygon=polygon,
            circle=self._txt(area, "cap:circle"),
            geocode=geocode,
        )

    @staticmethod
    def _txt(element, xpath: str) -> str | None:
        node = element.find(xpath, NS)
        if node is None or node.text is None:
            return None
        return node.text.strip()
