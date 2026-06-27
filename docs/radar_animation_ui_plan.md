# Radar Animation UI Plan

## Goal

Add optional animated radar effects to make the map more readable and visually alive. The animation should help users quickly identify active radar emitters, selected units, and detection coverage without changing the underlying simulation results.

This phase is UI-only by default. It should not change detection logic, weapon logic, or electromagnetic calculations unless explicitly enabled in a later gameplay phase.

## Design Principles

- Animation should clarify, not distract.
- Users must be able to turn it on or off from the UI.
- Static radar range circles should remain available for precise reading.
- Animation should work with the existing radar highlight, jammer overlay, and communications overlay.
- Performance should remain smooth with many units on the map.

## Current Behavior

- Radar/detection range is drawn as a static solid blue/red circle.
- Selected unit radar range can be highlighted with a brighter ring.
- Jammer range is drawn as a dashed amber/magenta circle.
- Communications/shared-awareness overlay has its own toggle and visual layer.
- There is no animated radar sweep or pulse effect.

## Proposed UI Option

Add a checkbox in the layer panel:

```text
☑ 雷达动态效果
```

Recommended behavior:

- Enabled by default during development.
- User can disable it when they want a cleaner tactical map.
- If `显示雷达范围圈` is off, radar animation should also be hidden.
- If no unit is selected, show subtle animation for active radar units only.
- If a unit is selected, emphasize that unit's radar animation more strongly.

## Animation Types

### 1. Radar Sweep

Draw a rotating wedge inside the radar circle.

Suggested style:

- Blue side: translucent cyan/blue wedge.
- Red side: translucent red/orange wedge.
- Selected unit: brighter yellow/cyan sweep.
- Sweep angle rotates continuously based on simulation time or wall-clock timer.

Example logic:

```text
sweep_angle = (animation_time * sweep_speed_deg_per_s + unit_offset) % 360
```

Recommended defaults:

- `sweep_speed_deg_per_s = 90`
- `sweep_width_deg = 24`
- `alpha = 35` for normal unit
- `alpha = 80` for selected unit

### 2. Radar Pulse

Draw a faint expanding pulse ring from the unit position.

Suggested style:

- Pulse expands from center to radar radius.
- Alpha fades as pulse grows.
- Selected unit pulse is brighter.

Example logic:

```text
pulse_phase = (animation_time * pulse_speed + unit_offset) % 1.0
pulse_radius = radar_radius_px * pulse_phase
pulse_alpha = 100 * (1 - pulse_phase)
```

Recommended defaults:

- `pulse_speed = 0.35 cycles/s`
- Normal pulse alpha max: `45`
- Selected pulse alpha max: `110`

### 3. Detected Contact Flash

When a unit detects a target, briefly flash a marker around the detected target.

Suggested style:

- Small ring around target.
- Text label: `DETECTED`
- Fade out over 1–2 seconds.

This can be added after sweep/pulse because it needs event tracking.

## Recommended Phase 1 Scope

Implement only:

1. UI toggle for radar animation.
2. Animated sweep wedge for active radar units.
3. Stronger sweep/pulse for selected unit.
4. No changes to detection rules.

Leave detected-contact flash for a later small pass.

## Data And State

No scenario JSON changes are required for the first UI-only version.

Add UI state to `MapCanvas`:

- `show_radar_animation: bool`
- `radar_animation_time: float`

Optional later per-unit fields:

- `radar_animation_enabled: bool`
- `radar_sweep_speed: float`
- `radar_emission_mode: str`

## Drawing Rules

Only animate units when:

```text
unit.alive == true
unit.radar_on == true
detection_range_nm or range_nm > 0
show_radar_ranges == true
show_radar_animation == true
```

Layer order:

1. Base map
2. Static radar range circles
3. Radar animation sweep/pulse
4. Jammer range circles
5. Communications overlay
6. Routes, weapons, units, impacts, labels

This keeps animation below unit icons but above the static radar fill.

## UI Changes

### `ui/main_window.py`

- Add `radar_animation_checkbox` under the existing radar range toggle.
- Label: `雷达动态效果`
- Connect it to `MapCanvas.set_radar_animation_visible`.

### `ui/map_canvas.py`

- Add `show_radar_animation = True`.
- Add `set_radar_animation_visible(visible: bool)`.
- Add `_draw_radar_animation_layer(painter)`.
- Reuse existing range-to-pixel radius calculation.
- Use `simulation_seconds` for deterministic animation during playback.
- If playback is paused, keep the last animation frame static.

## Performance Notes

- Avoid expensive gradients for every unit if many units exist.
- Use simple `QPainterPath` wedge or `drawPie` where possible.
- Skip animation when radius is extremely large and mostly off-screen.
- Skip dead units.
- Keep alpha low to avoid covering map details.

## Visual Style

Suggested colors:

- Blue radar sweep: `#38bdf8`
- Red radar sweep: `#fb7185`
- Selected radar sweep: `#facc15`
- Pulse outline: same color as side, low alpha

Suggested sizes:

- Sweep width: `24°`
- Selected sweep width: `34°`
- Normal pen width: `1.4`
- Selected pen width: `2.4`

## Verification Plan

### Manual Checks

1. Launch app and confirm radar animation appears when toggle is on.
2. Turn `雷达动态效果` off and confirm animation disappears.
3. Turn `显示雷达范围圈` off and confirm animation also disappears.
4. Click a unit and confirm its radar animation is brighter than others.
5. Pause playback and confirm animation stops or remains stable.
6. Confirm jammer and communications overlays remain readable.

### Automated Smoke Checks

1. `ui/map_canvas.py` compiles.
2. `ui/main_window.py` compiles.
3. `MapCanvas` exposes `set_radar_animation_visible`.
4. Toggling animation updates `show_radar_animation`.

## Implementation Order

1. Add UI state and setter in `MapCanvas`.
2. Add checkbox in layer panel.
3. Add radar animation drawing layer.
4. Tune colors and alpha.
5. Verify with selected and unselected units.
6. Run compile checks.

## Out Of Scope

- Changing radar detection probability.
- Different radar scan rates by equipment class.
- Directional radar sectors.
- Track flash on detection event.
- Audio/alert effects.
- Persisting UI preference.

