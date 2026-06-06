from __future__ import annotations

from pathlib import Path


def get_package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_map_asset_path() -> Path:
    return get_package_root() / "data" / "layers" / "offline_map.json"


def get_default_scenario_path() -> Path:
    return get_package_root() / "data" / "scenarios" / "taiwan_fujian_demo.json"


def get_default_layers_path() -> Path:
    return get_package_root() / "data" / "layers" / "routes.json"
