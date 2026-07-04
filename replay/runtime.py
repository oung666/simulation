from __future__ import annotations

from copy import deepcopy


class ReplayRuntime:
    def __init__(self, replay) -> None:
        self.replay = replay

    def seek(self, target_time: float) -> dict:
        snapshot = self.replay.snapshots[0]
        for current in self.replay.snapshots:
            if current.time <= target_time:
                snapshot = current
            else:
                break

        state = {
            "current_time": target_time,
            "units": deepcopy(snapshot.unit_states),
            "flying_weapons": deepcopy(snapshot.flying_weapon_states),
            "missions": deepcopy(snapshot.mission_states),
            "contacts": deepcopy(snapshot.contact_track_states),
        }

        for event in self.replay.event_stream:
            if snapshot.time < event.time <= target_time and event.event_type == "unit_destroyed":
                for unit in state["units"]:
                    if unit.get("unit_id") == event.target_id:
                        unit["alive"] = False
        return state
