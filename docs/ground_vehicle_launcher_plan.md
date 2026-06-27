# Ground Vehicle And Missile Launcher Plan

## Goal

Add mobile land combat units such as HIMARS, MLRS, TEL launchers, mobile radar vehicles, and command vehicles. This expands the simulation from air/sea/static land targets into a basic land-strike model while staying compatible with the current `CombatUnit` dataclass and scenario JSON format.

## Scope

- In: add a new `ground_vehicle` unit type, ground vehicle database defaults, map rendering, terrain validation, engagement rules, and one demo launcher unit.
- Out: detailed road routing, counter-battery radar, reload logistics, convoy behavior, ballistic trajectory modeling, and full ground maneuver tactics.

## Modeling Decision

A missile launcher such as HIMARS should be modeled as a **platform**, not as the missile itself.

- Platform: `type: "ground_vehicle"`, `class_name: "HIMARS"`
- Weapons: `GMLRS`, `ATACMS`, `PrSM`, or other missile templates

This keeps the existing platform/weapon split consistent with aircraft, ships, and facilities.

## Proposed Unit Types

Use one new generic unit type first:

```text
ground_vehicle
```

Different roles can be represented by `class_name` or future `role` fields:

- `HIMARS`
- `M270 MLRS`
- `Iskander TEL`
- `DF-16 TEL`
- `PCL-191`
- `Command Vehicle`
- `Mobile Radar Vehicle`
- `SAM Launcher Vehicle`

## Proposed Data Defaults

Create `core/db/_ground_vehicles.py` with initial entries:

- `HIMARS`: mobile rocket artillery, moderate speed, low radar range, land-attack weapons
- `M270 MLRS`: heavier rocket artillery
- `Iskander TEL`: short-range ballistic missile launcher
- `DF-16 TEL`: ballistic missile launcher
- `PCL-191`: long-range rocket artillery
- `Command Vehicle`: command node, datalink capable, low weapon capability
- `Mobile Radar Vehicle`: radar-capable, possible command node

Recommended default fields:

- `speed`
- `range`
- `detection_range_nm`
- `radar_on`
- `rcs`
- `jammer_power`
- `jammer_range_nm`
- `ew_resistance`
- `comms_on`
- `comms_range_nm`
- `datalink`
- `command_node`
- `comms_resistance`

## Scenario Example

```json
{
  "id": "blue-himars-01",
  "name": "Blue HIMARS-01",
  "side": "blue",
  "type": "ground_vehicle",
  "class_name": "HIMARS",
  "motion": "stationary",
  "position": [121.0, 24.2],
  "speed": 45,
  "range_nm": 2,
  "detection_range_nm": 15,
  "weapons": [
    {
      "weapon_class": "GMLRS",
      "name": "GMLRS",
      "speed": 1800,
      "range_nm": 43,
      "lethality": 0.7,
      "max_quantity": 6,
      "current_quantity": 6
    }
  ]
}
```

## Action Items

- [ ] Add `core/db/_ground_vehicles.py` with initial launcher, radar, and command vehicle templates.
- [ ] Register `ground_vehicle` in `core/db/__init__.py` so scenario loading can apply DB defaults.
- [ ] Update terrain validation so `ground_vehicle` must deploy and route on land.
- [ ] Update `ui/map_canvas.py` unit symbol rendering to draw a distinct ground vehicle icon.
- [ ] Update `controllers/combat_controller.py` `_can_target()` so ground vehicles can be targeted by aircraft, ships, facilities, and other ground launchers.
- [ ] Add ground vehicle launch behavior using existing `WeaponTemplate` and `FlyingWeapon` flow.
- [ ] Add or extend weapon templates for `GMLRS`, `ATACMS`, `PrSM`, `Iskander`, `DF-16`, and `PCL-191` if needed.
- [ ] Add one or two demo `ground_vehicle` units to `data/scenarios/taiwan_fujian_demo.json`.
- [ ] Verify blue/red perspective behavior: friendly ground vehicles show as real units, enemy ground vehicles appear only as contacts unless in god view.
- [ ] Run `python -m compileall -q app.py main.py core controllers engine ui` and a manual map check.

## Engagement Rules

Initial conservative rules:

- Aircraft can attack `ground_vehicle`.
- Ships can attack `ground_vehicle` if weapon range allows.
- Facilities can attack `ground_vehicle`.
- Ground vehicles can attack `ship`, `facility`, `airbase`, and `ground_vehicle`.
- Ground vehicles should not attack aircraft by default unless their class or weapons represent air defense.

Future refinement:

- Add `role` or `allowed_target_types` to distinguish rocket artillery, SAM vehicles, radar vehicles, and command vehicles.

## UI Behavior

- God view shows exact ground vehicle position, route, weapons, and status.
- Blue/red views show friendly ground vehicles normally.
- Enemy ground vehicles show only as side-specific contacts with last-known position, confidence, freshness, and source.
- Enemy ground vehicle contact popups remain read-only.

## Risks And Edge Cases

- Current movement logic does not model roads, so moving launchers may cross unrealistic terrain unless terrain validation is strict.
- Current weapon flight model is simplified and may not represent ballistic missile arcs.
- Without reload logistics, rocket artillery may be too simple after firing all rounds.
- Without shoot-and-scoot behavior, mobile launchers may behave like static facilities.

## Future Extensions

- Shoot-and-scoot behavior after launch.
- Counter-battery detection from launch events.
- Reload vehicles and ammo depots.
- Road-following movement.
- Launcher setup/pack-up time.
- Separate radar vehicle, launcher vehicle, command vehicle, and resupply vehicle roles.
