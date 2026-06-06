from __future__ import annotations

import math
from dataclasses import dataclass


TILE_SIZE = 256
MAX_LATITUDE = 85.05112878


@dataclass(frozen=True)
class LonLat:
    lon: float
    lat: float


@dataclass(frozen=True)
class ScreenPoint:
    x: float
    y: float


def clamp_latitude(lat: float) -> float:
    return max(-MAX_LATITUDE, min(MAX_LATITUDE, lat))


def lonlat_to_world(point: LonLat, zoom: float) -> ScreenPoint:
    scale = TILE_SIZE * (2.0**zoom)
    lat = math.radians(clamp_latitude(point.lat))
    x = (point.lon + 180.0) / 360.0 * scale
    y = (1.0 - math.log(math.tan(lat) + 1.0 / math.cos(lat)) / math.pi) / 2.0 * scale
    return ScreenPoint(x, y)


def world_to_lonlat(point: ScreenPoint, zoom: float) -> LonLat:
    scale = TILE_SIZE * (2.0**zoom)
    lon = point.x / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * point.y / scale
    lat = math.degrees(math.atan(math.sinh(n)))
    return LonLat(lon, lat)


def interpolate_route(points: list[LonLat], progress: float) -> LonLat:
    if not points:
        return LonLat(0.0, 0.0)
    if len(points) == 1:
        return points[0]

    progress = progress % 1.0
    segment_count = len(points) - 1
    raw_index = progress * segment_count
    index = min(int(raw_index), segment_count - 1)
    local_t = raw_index - index
    start = points[index]
    end = points[index + 1]
    return LonLat(
        start.lon + (end.lon - start.lon) * local_t,
        start.lat + (end.lat - start.lat) * local_t,
    )
