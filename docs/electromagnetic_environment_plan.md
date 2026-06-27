# Electromagnetic Environment Upgrade Plan

## Goal

Add a first-pass electromagnetic environment model to the simulation so radar detection and weapon effectiveness can be affected by radar state, target signature, electronic attack, and electronic protection.

This first phase should stay small and deterministic enough to validate quickly. It should not introduce full RF propagation, spectrum management, or probabilistic sensor fusion yet.

## Current Behavior

- Unit detection is mostly range based through `detection_range_nm`.
- Weapons use their configured range and lethality without considering jamming or target electronic protection.
- The map draws unit detection circles, routes, weapons, and impacts, but has no electromagnetic layer.
- Unit attributes come from scenario JSON plus the newly added equipment database defaults.

## Phase 1 Scope

### Data Model

Extend `CombatUnit` with electromagnetic fields:

- `radar_on: bool`
- `rcs: float`
- `jammer_power: float`
- `jammer_range_nm: float`
- `ew_resistance: float`

Recommended defaults:

- Aircraft: radar on, moderate `rcs`, low jammer unless specified.
- Ships/facilities: radar on, larger `rcs`, possible higher jammer range.
- Airbases: radar off or passive by default unless explicitly configured.

### Scenario And DB Loading

- Read EM fields from scenario JSON when present.
- Add EM defaults to `core/db` normalization so equipment DB defaults can supply missing values.
- Keep the existing precedence rule: scenario JSON overrides DB defaults.
- Existing scenario files should continue loading without changes.

### Detection Logic

Replace fixed detection checks with an effective range calculation:

```text
effective_detection_range =
  detection_range_nm * rcs_factor * jammer_factor
```

Suggested initial factors:

- `rcs_factor = clamp(sqrt(target.rcs), 0.35, 1.0)` so the visible radar circle remains the maximum detection boundary in Phase 1.
- `jammer_factor = clamp(1 - jammer_pressure + ew_resistance, 0.25, 1.0)`
- `jammer_pressure` comes from hostile jammers that cover the detector or the target.

If `radar_on` is false, active radar detection should fail or be sharply reduced.

### Weapon Effectiveness

Adjust terminal lethality for radar-guided or generic weapons:

```text
effective_lethality = base_lethality * weapon_jammer_factor
```

For phase 1, all guided weapons can use the same simplified factor. Later phases can split guidance types.

### UI Layer

Add a simple electromagnetic overlay:

- Draw jammer range circles for units with `jammer_range_nm > 0`.
- Use a distinct color from radar range, for example amber or magenta with low alpha.
- Add popup fields for:
  - Radar: ON/OFF
  - RCS
  - Jammer Range
  - EW Resistance

### Status And Debugging

Add lightweight debug visibility:

- Combat log message when a unit is detected under jamming.
- Optional debug text in the unit popup showing effective detection range.

## Out Of Scope For Phase 1

- Detailed RF frequency bands.
- Terrain masking for radar.
- Directional antennas or jammer sectors.
- False targets and deception.
- Communications network modeling.
- AI decisions for radar silence or jamming tactics.

## Proposed File Changes

### `core/scenario.py`

- Add EM fields to `CombatUnit`.
- Load EM fields with JSON-over-DB precedence.

### `core/db/__init__.py`

- Return EM defaults in `get_unit_attributes`.
- Use conservative category defaults when exact class match is unavailable.

### `engine/engagement.py`

- Add helpers for jammer pressure, effective detection range, and effective lethality.
- Update `is_detected` and `weapon_endgame` to use the EM model.

### `controllers/combat_controller.py`

- Pass enough context into detection and weapon resolution so nearby hostile jammers can affect outcomes.
- Keep existing combat log behavior stable.

### `ui/map_canvas.py`

- Draw jammer range circles as a new overlay near the existing range layer.
- Keep radar range visibility toggle behavior unchanged unless a separate EM toggle is added.

### `ui/unit_info_popup.py`

- Add EM fields to the default detail view.
- If edit support is extended, allow editing EM values in a later pass.

## Verification Plan

### Automated Smoke Tests

1. Existing default scenario loads unchanged.
2. A unit with `radar_on=false` does not actively detect a target at normal radar range.
3. A hostile jammer inside range reduces effective detection range.
4. JSON EM fields override DB defaults.
5. A guided weapon's effective lethality is reduced under jamming.

### Manual Checks

1. Launch the app and confirm the map renders normally.
2. Toggle or configure a jammer unit and confirm the jammer ring appears.
3. Compare combat logs for the same encounter with and without jamming.
4. Open a unit popup and confirm EM fields are visible and readable.

## Implementation Order

1. Add EM fields and DB defaults.
2. Add effective detection helper functions.
3. Apply EM logic to detection.
4. Apply EM logic to weapon terminal lethality.
5. Draw jammer range overlay.
6. Add popup EM fields.
7. Run smoke tests and a short manual app check.
