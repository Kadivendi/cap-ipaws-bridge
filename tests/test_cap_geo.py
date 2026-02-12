"""Tests for CAP geographic polygon and circle processing."""
import pytest
import math
from modules.cap.geo import (
    Coordinate, Polygon, Circle,
    parse_cap_polygon, parse_cap_circle,
    haversine_km, encode_zone_id, recipient_in_zone,
)


class TestCoordinate:
    def test_valid_coordinate(self):
        c = Coordinate(lat=34.05, lon=-118.24)
        assert c.lat == pytest.approx(34.05)

    def test_invalid_latitude_raises(self):
        with pytest.raises(ValueError):
            Coordinate(lat=91.0, lon=0.0)

    def test_invalid_longitude_raises(self):
        with pytest.raises(ValueError):
            Coordinate(lat=0.0, lon=181.0)


class TestPolygon:
    def _la_polygon(self):
        return Polygon(coordinates=[
            Coordinate(34.05, -118.50),
            Coordinate(34.20, -118.50),
            Coordinate(34.20, -118.10),
            Coordinate(34.05, -118.10),
            Coordinate(34.05, -118.50),
        ])

    def test_centroid(self):
        poly = self._la_polygon()
        c = poly.centroid
        assert 34.05 <= c.lat <= 34.20
        assert -118.50 <= c.lon <= -118.10

    def test_bounding_box(self):
        poly = self._la_polygon()
        min_lat, min_lon, max_lat, max_lon = poly.bounding_box
        assert min_lat == pytest.approx(34.05)
        assert max_lat == pytest.approx(34.20)

    def test_point_inside_polygon(self):
        poly = self._la_polygon()
        inside = Coordinate(lat=34.10, lon=-118.30)
        assert poly.contains_point(inside) is True

    def test_point_outside_polygon(self):
        poly = self._la_polygon()
        outside = Coordinate(lat=35.0, lon=-120.0)
        assert poly.contains_point(outside) is False


class TestHaversine:
    def test_same_point_distance_zero(self):
        la = Coordinate(34.05, -118.24)
        assert haversine_km(la, la) == pytest.approx(0.0, abs=1e-6)

    def test_la_to_ny_approximately_correct(self):
        la = Coordinate(34.05, -118.24)
        ny = Coordinate(40.71, -74.00)
        dist = haversine_km(la, ny)
        assert 3900 < dist < 4000  # ~3940 km

    def test_symmetry(self):
        a = Coordinate(37.77, -122.41)
        b = Coordinate(47.60, -122.33)
        assert haversine_km(a, b) == pytest.approx(haversine_km(b, a), rel=1e-9)


class TestParseCapPolygon:
    def test_valid_polygon(self):
        text = "34.05,-118.24 34.10,-118.20 34.08,-118.30 34.05,-118.24"
        poly = parse_cap_polygon(text)
        assert len(poly.coordinates) == 4
        assert poly.coordinates[0].lat == pytest.approx(34.05)

    def test_invalid_pair_raises(self):
        with pytest.raises((ValueError, IndexError)):
            parse_cap_polygon("bad_data")


class TestParseCapCircle:
    def test_valid_circle(self):
        circle = parse_cap_circle("34.05,-118.24 25.0")
        assert circle.center.lat == pytest.approx(34.05)
        assert circle.radius_km == pytest.approx(25.0)


class TestRecipientInZone:
    def test_recipient_inside_circle(self):
        circle = Circle(center=Coordinate(34.05, -118.24), radius_km=50.0)
        nearby = Coordinate(34.10, -118.20)
        assert recipient_in_zone(nearby, circle) is True

    def test_recipient_outside_circle(self):
        circle = Circle(center=Coordinate(34.05, -118.24), radius_km=5.0)
        far = Coordinate(40.71, -74.00)
        assert recipient_in_zone(far, circle) is False
