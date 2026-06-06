from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qt_frontend_v6.core.layers import load_layer_document, route_lookup
from qt_frontend_v6.core.paths import get_default_layers_path, get_default_scenario_path
from qt_frontend_v6.core.scenario import load_scenario
from qt_frontend_v6.controllers.motion import MotionController


def main() -> int:
    scenario = load_scenario(get_default_scenario_path())
    layers = load_layer_document(get_default_layers_path())
    controller = MotionController(route_lookup(layers))

    print("=== V6 together motion demo ===")
    print(f"scenario={scenario.name}")
    print(f"routes={len(layers.routes)} units={len(scenario.units)}")
    print()

    for seconds in [0, 30, 60, 90, 120]:
        print(f"[t={seconds:>3}s]")
        for unit in scenario.units:
            position = controller.position_for(unit, float(seconds))
            print(
                f"{unit.unit_id:<16} {unit.name:<8} "
                f"motion={unit.motion:<14} route={unit.route_id or '-':<24} "
                f"lon={position.lon:.6f} lat={position.lat:.6f}"
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
