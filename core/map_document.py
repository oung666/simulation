from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simulation.core.geo import LonLat


@dataclass(frozen=True)
class MapFeature:
    kind: str
    name: str
    coordinates: list[LonLat]
    style: str


@dataclass(frozen=True)
class MapDocument:
    name: str
    center: LonLat
    bounds: tuple[float, float, float, float]
    min_zoom: float
    max_zoom: float
    tile_root: Path
    tile_source: str
    features: list[MapFeature]


def _read_point(raw: list[float]) -> LonLat:
    return LonLat(float(raw[0]), float(raw[1]))


def load_map_document(path: Path) -> MapDocument:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    features: list[MapFeature] = []
    for raw_feature in payload.get("features", []):
        features.append(
            MapFeature(
                kind=str(raw_feature.get("kind", "line")),
                name=str(raw_feature.get("name", "")),
                coordinates=[_read_point(point) for point in raw_feature.get("coordinates", [])],
                style=str(raw_feature.get("style", raw_feature.get("kind", "line"))),
            )
        )

    bounds = payload.get("bounds", [117.0, 20.0, 124.5, 27.0])
    return MapDocument(
        name=str(payload.get("name", path.stem)),
        center=_read_point(payload.get("center", [121.0, 23.8])),
        bounds=(float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])),
        min_zoom=float(payload.get("min_zoom", 6)),
        max_zoom=float(payload.get("max_zoom", 13)),
        tile_root=(path.parent / str(payload.get("tile_root", "tiles"))).resolve(),
        tile_source=str(payload.get("tile_source", "")),
        features=features,
    )

