# Communications And Shared Situational Awareness Plan

## Goal

Add a second-phase communications and shared situational awareness model so detection is no longer only a local unit event. Units should be able to share contacts through command networks, but that sharing should depend on communication range, datalink capability, command nodes, jamming, and network health.

This phase should stay deterministic and understandable on the map. It should not introduce full radio waveform modeling, encryption, routing protocols, or probabilistic intelligence fusion yet.

## Design Principle

Phase 1 answered:

```text
Can this unit personally detect this target?
```

Phase 2 should answer:

```text
Can this side know about this target through any friendly sensor and communication path?
```

So the system should distinguish three states:

- **Undetected**: No friendly unit has detected the target.
- **Locally Detected**: This unit's own sensors detect the target.
- **Shared Contact**: Another friendly unit detected the target and shared it through the network.

This difference matters because a unit may be able to launch or maneuver based on shared information even when its own radar does not see the target.

## Current Behavior

- Detection is evaluated directly between a shooter and target.
- A unit generally needs its own detection before selecting a weapon.
- Combat log records detection events, but there is no contact memory or side-level intelligence picture.
- Electromagnetic jamming affects detection and weapon terminal effectiveness, but not communications.
- The map shows radar range and jammer range, but not communications links or shared contacts.

## Phase 2 Scope

### Data Model

Extend `CombatUnit` with communication and network fields:

- `comms_on: bool`
- `comms_range_nm: float`
- `datalink: bool`
- `command_node: bool`
- `comms_power: float`
- `comms_resistance: float`
- `contact_share_delay_s: float`

Recommended defaults:

- Aircraft: datalink capable, medium communication range, not command node by default.
- Ships: datalink capable, long communication range, some ships may be command nodes.
- Facilities/radar stations: command node capable, long communication range, strong resistance.
- Airbases: command node capable, long communication range, high resistance.

Optional later fields:

- `network_id: str`
- `relay_capable: bool`
- `emission_control: str`
- `contact_memory_s: float`

For Phase 2, `side` can act as the default network. A more detailed `network_id` can be added later if mixed coalitions or separate task groups are needed.

### Contact Model

Add a side-level contact picture that stores what each side currently knows:

```text
ContactTrack
  target_id
  side
  last_known_position
  last_detected_time
  source_unit_id
  confidence
  track_type
  shared
```

Suggested track states:

- `local`: detected directly by the observing unit.
- `shared`: received through communications.
- `stale`: previously known but not refreshed recently.
- `lost`: expired from the contact picture.

Suggested confidence model for Phase 2:

```text
confidence = clamp(sensor_quality * comms_quality * freshness_factor, 0.0, 1.0)
```

Keep it simple at first:

- Direct radar detection creates confidence `1.0`.
- Shared contacts start at `0.8`.
- Stale contacts decay over time.
- Contacts expire after a configured memory window.

### Communication Link Logic

Two friendly units can share contacts when:

```text
same side
comms_on == true for sender and receiver
datalink == true for sender and receiver
distance <= effective_comms_range
```

Effective communication range:

```text
effective_comms_range =
  comms_range_nm * comms_jammer_factor
```

Suggested factor:

```text
comms_jammer_factor =
  clamp(1 - hostile_comms_pressure + comms_resistance, 0.2, 1.0)
```

`hostile_comms_pressure` should come from hostile jammers that cover the sender, receiver, or line area. For Phase 2, checking whether the jammer covers either endpoint is enough.

### Network Propagation

Use deterministic one-step or limited relay sharing:

1. Each unit performs local detection using Phase 1 radar logic.
2. Local detections create or refresh contact tracks.
3. Contacts are shared across valid friendly communication links.
4. Command nodes can relay shared contacts to other valid links.
5. Contact confidence decays if not refreshed.

Recommended Phase 2 rule:

- Direct sender-to-receiver sharing is always allowed when link is valid.
- One relay through a `command_node` is allowed.
- Unlimited multi-hop routing is out of scope for now.

This keeps behavior easy to understand and prevents the whole side from instantly knowing everything.

### Engagement Rules

Add a policy switch so shared contacts do not immediately make every unit omniscient:

```text
engagement_policy:
  require_local_detection_for_launch: bool
  allow_shared_contact_launch: bool
  min_shared_confidence_for_launch: float
```

Recommended initial behavior:

- Aircraft-to-aircraft combat should still prefer local detection.
- Long-range missile or strike launch may use shared contacts if confidence is high enough.
- If a weapon is launched on shared contact only, terminal effectiveness may be reduced unless the target is locally reacquired.

Example:

```text
allow_shared_contact_launch = true
min_shared_confidence_for_launch = 0.7
```

### Interaction With Electromagnetic Environment

Communications should be affected by the existing EM model, but not identical to radar detection:

- Radar jamming reduces detection.
- Communications jamming reduces contact sharing.
- A jammer can affect both if it has both radar-jamming and comms-jamming capability later.

For Phase 2, use existing `jammer_power` and `jammer_range_nm` as a shared simplified jamming source. Later phases can split:

- `radar_jammer_power`
- `comms_jammer_power`
- `gps_jammer_power`
- `jammer_band`

### UI Layer

Add map visibility for communication and shared contacts:

- Add a UI toggle for the communications/shared-awareness overlay.
- The user should be able to turn this layer on or off from the main UI, similar to the existing radar/range visibility control.
- When the toggle is off, hide communication range circles, datalink lines, and shared-contact markers while keeping the underlying simulation logic available.
- When a unit is selected, highlight its communication range.
- Draw valid friendly datalink lines from the selected unit.
- Use green/cyan lines for healthy links.
- Use amber/red dashed lines for degraded or jammed links.
- Mark shared contacts with a different icon or label, for example `SHARED`.
- Keep existing radar highlight behavior separate from communication highlight.

Suggested overlays:

- Radar range: existing solid blue/red.
- Jammer range: existing dashed amber/magenta.
- Selected communication range: cyan dashed circle.
- Active datalink: cyan line.
- Jammed datalink: orange dashed line.

Suggested UI option:

```text
☑ 通信/态势共享
```

Default recommendation:

- Enabled by default during development so behavior is visible.
- User can disable it when the map becomes visually crowded.
- Later, split it into separate toggles if needed:
  - Communication Range
  - Datalink Lines
  - Shared Contacts

### Popup Fields

Add communication fields to the unit popup:

- Comms: ON/OFF
- Datalink: YES/NO
- Command Node: YES/NO
- Comms Range
- Comms Resistance
- Shared Contacts Count

Optional debug fields:

- Active Links
- Jammed Links
- Contact Source
- Contact Confidence

### Combat Log And Debugging

Add concise log messages:

- `A detected B locally`
- `A shared B contact to C`
- `C received shared contact on B`
- `Link A -> C degraded by jamming`
- `Shared contact on B expired`

Avoid logging every repeated network propagation tick. Only log first share, major state changes, and expiry.

## Proposed File Changes

### `core/scenario.py`

- Add communication fields to `CombatUnit`.
- Load JSON fields with scenario-over-DB precedence.
- Keep old scenario files compatible.

### `core/db/__init__.py`

- Add category communication defaults.
- Normalize future DB fields like `commsRangeNm`, `datalink`, and `commandNode`.

### `core/contact.py`

- Add `ContactTrack` dataclass.
- Add helpers for freshness, confidence decay, and expiry.

### `engine/communications.py`

- Add communication link helpers:
  - `effective_comms_range_nm`
  - `comms_jammer_pressure`
  - `can_share_contact`
  - `build_network_links`

### `controllers/combat_controller.py`

- Maintain side contact pictures.
- Create tracks from local detections.
- Propagate shared contacts through valid links.
- Allow selected engagement logic to use shared contacts.
- Add combat log entries for first share and degraded links.

### `ui/map_canvas.py`

- Add `show_communications_overlay` state.
- Add `set_communications_overlay_visible(visible: bool)`.
- Draw selected unit communication range.
- Draw active datalink lines.
- Draw shared contact markers.

### `ui/main_window.py`

- Add a checkbox/menu action for the communications/shared-awareness overlay.
- Connect the UI option to `MapCanvas.set_communications_overlay_visible`.
- Persisting the preference can be added later if needed.

### `ui/unit_info_popup.py`

- Display communication fields and shared contact status.

## Verification Plan

### Automated Smoke Tests

1. Existing default scenario loads unchanged.
2. Two friendly units inside communication range share a detected contact.
3. A unit outside communication range does not receive the contact.
4. A command node can relay one hop.
5. A hostile jammer reduces effective communication range.
6. Shared contacts decay and expire when not refreshed.
7. JSON communication fields override DB defaults.

### Manual Checks

1. Launch the app and select a unit with communications enabled.
2. Toggle the communications/shared-awareness option on and off.
3. Confirm communication range, datalink lines, and shared contact markers hide when the option is off.
4. Confirm its communication range highlights separately from radar range when the option is on.
5. Confirm valid datalink lines appear between friendly units.
6. Move or configure units so a link breaks and verify the shared contact disappears after expiry.
7. Add a jammer and confirm communication links visually degrade.
8. Confirm popup shows communications fields clearly.

## Implementation Order

1. Add communication fields and DB defaults.
2. Add `ContactTrack` model.
3. Add communication link helpers.
4. Create local contact tracks from existing detection.
5. Propagate contacts through valid links.
6. Apply shared contacts to engagement policy.
7. Add UI toggle for communications overlay.
8. Draw communication range and datalink lines.
9. Add popup communication fields.
10. Run smoke tests and manual map checks.

## Out Of Scope For Phase 2

- Full spectrum/frequency band modeling.
- Encryption or cyber effects.
- Unlimited network routing.
- Probabilistic multi-sensor fusion.
- False contacts and deception tracks.
- Detailed AWACS or satellite sensor modeling.
- Directional antennas and terrain masking.

## Open Design Questions

- Should shared contacts allow immediate weapon launch, or only route/maneuver decisions?
- Should ships be command nodes by default, or only specific ship classes?
- How long should shared contacts remain valid after communications are lost?
- Should radar-off units still receive shared contacts while remaining passive?
- Should communication links be visible all the time or only for the selected unit?
