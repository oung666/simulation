from __future__ import annotations

from copy import deepcopy
from typing import Any

from simulation.replay.models import ReplayEvent, ReplayRecord, ReplaySnapshot


class ReplayRecorder:
    def __init__(self, snapshot_interval_seconds: float = 2.5) -> None:
        self.snapshot_interval_seconds = snapshot_interval_seconds
        self._active = False
        self._replay_id = ""
        self._scenario_name = ""
        self._started_at = ""
        self._initial_state: dict[str, Any] = {}
        self._snapshots: list[ReplaySnapshot] = []
        self._events: list[ReplayEvent] = []
        self._last_periodic_snapshot_time = 0.0
        self._recording_start_time = 0.0

    @property
    def active(self) -> bool:
        return self._active

    def start(
        self,
        replay_id: str,
        scenario_name: str,
        started_at: str,
        initial_state: dict[str, Any],
        initial_time: float = 0.0,
    ) -> None:
        self._active = True
        self._replay_id = replay_id
        self._scenario_name = scenario_name
        self._started_at = started_at
        self._recording_start_time = float(initial_time)
        self._initial_state = deepcopy(initial_state)
        self._snapshots = [self._snapshot_from_state(0.0, initial_state)]
        self._events = []
        self._last_periodic_snapshot_time = 0.0

    def cancel(self) -> None:
        self._active = False
        self._replay_id = ""
        self._scenario_name = ""
        self._started_at = ""
        self._initial_state = {}
        self._snapshots = []
        self._events = []
        self._last_periodic_snapshot_time = 0.0
        self._recording_start_time = 0.0

    def capture_periodic_snapshot(
        self,
        time: float,
        state: dict[str, Any],
    ) -> None:
        if not self._active:
            return
        relative_time = self._relative_time(time)
        if relative_time - self._last_periodic_snapshot_time < self.snapshot_interval_seconds:
            return
        self._snapshots.append(self._snapshot_from_state(relative_time, state))
        self._last_periodic_snapshot_time = relative_time

    def record_event(
        self,
        time: float,
        event_type: str,
        source_id: str,
        target_id: str,
        weapon_class: str,
        position: dict[str, float] | None,
        message: str,
        force_snapshot_state: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if not self._active:
            return
        relative_time = self._relative_time(time)
        self._events.append(
            ReplayEvent(
                time=relative_time,
                event_type=event_type,
                source_id=source_id,
                target_id=target_id,
                weapon_class=weapon_class,
                position=None if position is None else deepcopy(position),
                message=message,
                extra={} if extra is None else deepcopy(extra),
            )
        )
        if force_snapshot_state is not None:
            self._snapshots.append(self._snapshot_from_state(relative_time, force_snapshot_state))

    def finish(
        self,
        ended_at: str,
        duration_seconds: float,
        final_state: dict[str, Any],
        settlement_reason: str,
        final_snapshot_state: dict[str, Any] | None = None,
    ) -> ReplayRecord:
        snapshots = list(self._snapshots)
        relative_duration_seconds = self._relative_time(duration_seconds)
        if final_snapshot_state is not None:
            snapshots.append(
                self._snapshot_from_state(relative_duration_seconds, final_snapshot_state)
            )
        replay = ReplayRecord(
            replay_id=self._replay_id,
            scenario_name=self._scenario_name,
            started_at=self._started_at,
            ended_at=ended_at,
            settlement_reason=settlement_reason,
            duration_seconds=relative_duration_seconds,
            tick_interval_seconds=1.0,
            snapshot_interval_seconds=self.snapshot_interval_seconds,
            participants=[],
            initial_state=deepcopy(self._initial_state),
            snapshots=snapshots,
            event_stream=list(self._events),
            highlights=[],
            final_state=deepcopy(final_state),
        )
        self._active = False
        return replay

    def _relative_time(self, absolute_time: float) -> float:
        return max(0.0, float(absolute_time) - self._recording_start_time)

    @staticmethod
    def _snapshot_from_state(
        time: float,
        state: dict[str, Any],
    ) -> ReplaySnapshot:
        return ReplaySnapshot(
            time=time,
            clock_state={"current_time": time},
            unit_states=deepcopy(state.get("units", [])),
            flying_weapon_states=deepcopy(state.get("flying_weapons", [])),
            mission_states=deepcopy(state.get("missions", [])),
            contact_track_states=deepcopy(state.get("contacts", [])),
        )
