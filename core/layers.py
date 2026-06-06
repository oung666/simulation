from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qt_frontend_v6.core.geo import LonLat


@dataclass
class RouteLayerItem:
    route_id: str
    name: str
    side: str
    points: list[LonLat]
    visible: bool = True


@dataclass
class RangeLayerItem:
    owner_id: str
    side: str
    center: LonLat
    radius_nm: float
    visible: bool = True


@dataclass
class LayerDocument:
    routes: list[RouteLayerItem]
    ranges: list[RangeLayerItem]


def _read_point(raw: list[float]) -> LonLat:
    return LonLat(float(raw[0]), float(raw[1]))


def load_layer_document(path: Path) -> LayerDocument:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    routes: list[RouteLayerItem] = []
    for raw_route in payload.get("routes", []):
        routes.append(
            RouteLayerItem(
                route_id=str(raw_route["id"]),
                name=str(raw_route.get("name", raw_route["id"])),
                side=str(raw_route.get("side", "blue")).lower(),
                points=[_read_point(point) for point in raw_route.get("points", [])],
                visible=bool(raw_route.get("visible", True)),
            )
        )
    return LayerDocument(routes=routes, ranges=[])


def route_lookup(document: LayerDocument) -> dict[str, RouteLayerItem]:
    return {route.route_id: route for route in document.routes}


def upsert_route(document: LayerDocument, route: RouteLayerItem) -> None:
    for index, current in enumerate(document.routes):
        if current.route_id == route.route_id:
            document.routes[index] = route
            return
    document.routes.append(route)


def next_route_id(document: LayerDocument, side: str) -> str:
    prefix = f"{side.lower()}_"
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    max_index = 0
    for route in document.routes:
        match = pattern.match(route.route_id)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"{prefix}{max_index + 1:02d}"


def save_layer_document(document: LayerDocument, path: Path) -> None:
    payload = {
        "routes": [
            {
                "id": route.route_id,
                "name": route.name,
                "side": route.side,
                "visible": route.visible,
                "points": [[point.lon, point.lat] for point in route.points],
            }
            for route in document.routes
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
