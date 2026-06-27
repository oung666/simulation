from __future__ import annotations

import math
import random

from simulation.core.geo import LonLat


EARTH_RADIUS_KM = 6371.0
NM_TO_METERS = 1852


def nm_to_km(nm: float) -> float:
    """Convert nautical miles to kilometers."""
    return nm * NM_TO_METERS / 1000.0


def km_to_nm(km: float) -> float:
    """Convert kilometers to nautical miles."""
    return km * 1000.0 / NM_TO_METERS


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance between two coordinates in kilometers."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


def bearing_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return initial bearing from point 1 to point 2 in degrees."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def destination_point(lat: float, lon: float, distance_km: float, bearing: float) -> tuple[float, float]:
    """Return coordinate reached by moving from a point for distance along bearing."""
    angular_distance = distance_km / EARTH_RADIUS_KM
    bearing_rad = math.radians(bearing)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    dest_lat = math.asin(
        math.sin(lat_rad) * math.cos(angular_distance)
        + math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    dest_lon = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
        math.cos(angular_distance) - math.sin(lat_rad) * math.sin(dest_lat),
    )

    lon_deg = (math.degrees(dest_lon) + 540.0) % 360.0 - 180.0
    return math.degrees(dest_lat), lon_deg


def get_terminal_coordinates_from_distance_and_bearing(
    lat: float,
    lon: float,
    distance_nm: float,
    bearing: float,
) -> LonLat:
    """Return lon/lat reached by moving distance_nm along bearing."""
    dest_lat, dest_lon = destination_point(lat, lon, nm_to_km(distance_nm), bearing)
    return LonLat(dest_lon, dest_lat)


def point_in_polygon(point: LonLat, polygon: list[LonLat]) -> bool:
    """Return whether point is inside polygon using the ray-casting algorithm."""
    if len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i, vertex in enumerate(polygon):
        previous = polygon[j]
        crosses = (vertex.lat > point.lat) != (previous.lat > point.lat)
        if crosses:
            lon_at_lat = (previous.lon - vertex.lon) * (point.lat - vertex.lat) / (previous.lat - vertex.lat) + vertex.lon
            if point.lon < lon_at_lat:
                inside = not inside
        j = i
    return inside


def generate_random_coordinates_within_polygon(polygon: list[LonLat], max_attempts: int = 200) -> LonLat:
    """Generate a random coordinate inside a polygon by bounded rejection sampling."""
    if not polygon:
        return LonLat(0.0, 0.0)
    if len(polygon) < 3:
        return polygon[0]

    min_lon = min(point.lon for point in polygon)
    max_lon = max(point.lon for point in polygon)
    min_lat = min(point.lat for point in polygon)
    max_lat = max(point.lat for point in polygon)
    for _ in range(max_attempts):
        candidate = LonLat(
            random.uniform(min_lon, max_lon),
            random.uniform(min_lat, max_lat),
        )
        if point_in_polygon(candidate, polygon):
            return candidate
    return LonLat(
        sum(point.lon for point in polygon) / len(polygon),
        sum(point.lat for point in polygon) / len(polygon),
    )


def next_position(lat1: float, lon1: float, lat2: float, lon2: float, speed_knots: float) -> tuple[float, float]:
    """Move one simulated second from point 1 toward point 2 at speed_knots."""
    distance_to_target_km = haversine_distance_km(lat1, lon1, lat2, lon2)
    step_km = nm_to_km(max(0.0, speed_knots) / 3600.0)
    if step_km <= 0.0 or distance_to_target_km <= step_km:
        return lat2, lon2
    bearing = bearing_between(lat1, lon1, lat2, lon2)
    return destination_point(lat1, lon1, step_km, bearing)
