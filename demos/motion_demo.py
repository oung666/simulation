from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.core.layers import load_layer_document, route_lookup
from simulation.core.paths import get_default_layers_path, get_default_scenario_path
from simulation.core.scenario import load_scenario
from simulation.controllers.motion import MotionController


def main() -> int:
    scenario = load_scenario(get_default_scenario_path())
    layers = load_layer_document(get_default_layers_path())
    controller = MotionController(route_lookup(layers))

    print("=== V6 together motion demo ===")
    print(f"scenario={scenario.name}")
    print(f"routes={len(layers.routes)} units={len(scenario.units)}")
    print()

    previous_seconds = 0
    for seconds in [0, 30, 60, 90, 120]:
        for _ in range(seconds - previous_seconds):
            for unit in scenario.units:
                controller.advance(unit, 1.0)
        previous_seconds = seconds
        print(f"[t={seconds:>3}s]")
        for unit in scenario.units:
            position = controller.position_for(unit)
            print(
                f"{unit.unit_id:<16} {unit.name:<8} "
                f"motion={unit.motion:<14} route={unit.route_id or '-':<24} "
                f"speed={unit.speed:g} kts lon={position.lon:.6f} lat={position.lat:.6f}"
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

