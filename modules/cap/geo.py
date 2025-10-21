"""
CAP Geographic Polygon Processing
Converts CAP 1.2 area polygons and circles into PostGIS geometries,
computes region intersections, and encodes compact zone identifiers.
"""
import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

WGS84_EARTH_RADIUS_KM = 6371.0


@dataclass
class Coordinate:
    lat: float
    lon: float

    def __post_init__(self):
        if not (-90 <= self.lat <= 90):
            raise ValueError(f"Latitude out of range: {self.lat}")
        if not (-180 <= self.lon <= 180):
            raise ValueError(f"Longitude out of range: {self.lon}")


@dataclass
class Polygon:
    coordinates: list[Coordinate] = field(default_factory=list)

    @property
    def centroid(self) -> Coordinate:
        n = len(self.coordinates)
        if n == 0:
            raise ValueError("Cannot compute centroid of empty polygon")
        return Coordinate(
            lat=sum(c.lat for c in self.coordinates) / n,
            lon=sum(c.lon for c in self.coordinates) / n,
        )

    @property
    def bounding_box(self) -> tuple[float, float, float, float]:
        """Returns (min_lat, min_lon, max_lat, max_lon)."""
        lats = [c.lat for c in self.coordinates]
        lons = [c.lon for c in self.coordinates]
        return min(lats), min(lons), max(lats), max(lons)

    def contains_point(self, point: Coordinate) -> bool:
        """Ray-casting algorithm for point-in-polygon test."""
        x, y = point.lon, point.lat
        n = len(self.coordinates)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = self.coordinates[i].lon, self.coordinates[i].lat
            xj, yj = self.coordinates[j].lon, self.coordinates[j].lat
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside


@dataclass
class Circle:
    center: Coordinate
    radius_km: float


def parse_cap_polygon(polygon_text: str) -> Polygon:
    """Parse CAP 1.2 polygon string: 'lat,lon lat,lon ...'"""
    coords = []
    for pair in polygon_text.strip().split():
        parts = pair.split(",")
        if len(parts) != 2:
            raise ValueError(f"Invalid coordinate pair: {pair}")
        coords.append(Coordinate(lat=float(parts[0]), lon=float(parts[1])))
    return Polygon(coordinates=coords)


def parse_cap_circle(circle_text: str) -> Circle:
    """Parse CAP 1.2 circle string: 'lat,lon radius'"""
    parts = circle_text.strip().split()
    if len(parts) != 2:
        raise ValueError(f"Invalid circle format: {circle_text!r}")
    lat_lon = parts[0].split(",")
    return Circle(
        center=Coordinate(lat=float(lat_lon[0]), lon=float(lat_lon[1])),
        radius_km=float(parts[1]),
    )


def haversine_km(a: Coordinate, b: Coordinate) -> float:
    """Great-circle distance between two WGS-84 coordinates in km."""
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    dphi = math.radians(b.lat - a.lat)
    dlambda = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * WGS84_EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def encode_zone_id(area: Polygon | Circle) -> str:
    """Compact zone identifier for mesh routing (lat/lon truncated to 3dp)."""
    if isinstance(area, Circle):
        c = area.center
        return f"circ:{c.lat:.3f},{c.lon:.3f},{area.radius_km:.1f}km"
    centroid = area.centroid
    bbox = area.bounding_box
    diagonal_km = haversine_km(
        Coordinate(lat=bbox[0], lon=bbox[1]),
        Coordinate(lat=bbox[2], lon=bbox[3]),
    )
    return f"poly:{centroid.lat:.3f},{centroid.lon:.3f},{diagonal_km:.1f}km"


def recipient_in_zone(recipient_coord: Coordinate, area: Polygon | Circle) -> bool:
    """Check whether a recipient's coordinates fall within the alert zone."""
    if isinstance(area, Circle):
        return haversine_km(area.center, recipient_coord) <= area.radius_km
    return area.contains_point(recipient_coord)
