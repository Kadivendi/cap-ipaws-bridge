"""
CAP 1.2 composer.

Builds OASIS-compliant CAP XML from a structured Python payload so the
``/api/v1/compose`` endpoint and the (Wagtail-derived) composer UI can
publish alerts that pass FEMA IPAWS-OPEN schema validation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from lxml import etree

from .parser import CAP_NS


@dataclass
class ComposedAreaSpec:
    area_desc: str
    polygon: list[tuple[float, float]] = field(default_factory=list)
    circle: str | None = None  # "lat,lon radius_km"
    geocode: dict[str, str] = field(default_factory=dict)


@dataclass
class ComposedAlertSpec:
    sender: str
    headline: str
    description: str
    instruction: str
    severity: str = "Severe"
    urgency: str = "Immediate"
    certainty: str = "Observed"
    category: str = "Safety"
    event: str = "Emergency Action"
    status: str = "Actual"
    msg_type: str = "Alert"
    scope: str = "Public"
    language: str = "en-US"
    identifier: str | None = None
    sent: datetime | None = None
    areas: list[ComposedAreaSpec] = field(default_factory=list)


class CAPComposer:
    """Turn a :class:`ComposedAlertSpec` into CAP 1.2 XML."""

    def compose(self, spec: ComposedAlertSpec) -> str:
        nsmap = {None: CAP_NS}
        root = etree.Element("alert", nsmap=nsmap)

        self._sub(root, "identifier", spec.identifier or str(uuid.uuid4()))
        self._sub(root, "sender", spec.sender)
        self._sub(root, "sent", (spec.sent or datetime.now(timezone.utc)).isoformat())
        self._sub(root, "status", spec.status)
        self._sub(root, "msgType", spec.msg_type)
        self._sub(root, "scope", spec.scope)

        info = etree.SubElement(root, "info")
        self._sub(info, "language", spec.language)
        self._sub(info, "category", spec.category)
        self._sub(info, "event", spec.event)
        self._sub(info, "urgency", spec.urgency)
        self._sub(info, "severity", spec.severity)
        self._sub(info, "certainty", spec.certainty)
        self._sub(info, "headline", spec.headline)
        self._sub(info, "description", spec.description)
        self._sub(info, "instruction", spec.instruction)

        for area in spec.areas:
            self._append_area(info, area)

        return etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        ).decode("utf-8")

    def _append_area(self, info, area: ComposedAreaSpec) -> None:
        area_el = etree.SubElement(info, "area")
        self._sub(area_el, "areaDesc", area.area_desc)
        if area.polygon:
            poly_text = " ".join(f"{lat},{lon}" for lat, lon in area.polygon)
            self._sub(area_el, "polygon", poly_text)
        if area.circle:
            self._sub(area_el, "circle", area.circle)
        for name, value in area.geocode.items():
            g = etree.SubElement(area_el, "geocode")
            self._sub(g, "valueName", name)
            self._sub(g, "value", value)

    @staticmethod
    def _sub(parent, tag: str, text: str) -> None:
        el = etree.SubElement(parent, tag)
        el.text = text
