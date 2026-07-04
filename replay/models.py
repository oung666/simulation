from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ReplaySnapshot:
    time: float
    clock_state: dict[str, Any]
    unit_states: list[dict[str, Any]]
    flying_weapon_states: list[dict[str, Any]]
    mission_states: list[dict[str, Any]]
    contact_track_states: list[dict[str, Any]]


@dataclass
class ReplayEvent:
    time: float
    event_type: str
    source_id: str
    target_id: str
    weapon_class: str
    position: dict[str, float] | None
    message: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SideSummary:
    alive_count: int
    lost_count: int
    launch_count: int
    hit_count: int
    kill_count: int


@dataclass
class UnitBattleRow:
    unit_id: str
    name: str
    side: str
    unit_type: str
    class_name: str
    alive: bool
    kills: int
    destroyed: bool
    launches: int
    hits: int
    last_position: dict[str, float] | None
    final_mission_status: str


@dataclass
class ReplayRecord:
    replay_id: str
    scenario_name: str
    started_at: str
    ended_at: str
    settlement_reason: str
    duration_seconds: float
    tick_interval_seconds: float
    snapshot_interval_seconds: float
    participants: list[str]
    initial_state: dict[str, Any]
    snapshots: list[ReplaySnapshot]
    event_stream: list[ReplayEvent]
    highlights: list[dict[str, Any]]
    final_state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReplayRecord:
        return cls(
            replay_id=payload["replay_id"],
            scenario_name=payload["scenario_name"],
            started_at=payload["started_at"],
            ended_at=payload["ended_at"],
            settlement_reason=payload["settlement_reason"],
            duration_seconds=float(payload["duration_seconds"]),
            tick_interval_seconds=float(payload["tick_interval_seconds"]),
            snapshot_interval_seconds=float(payload["snapshot_interval_seconds"]),
            participants=list(payload["participants"]),
            initial_state=dict(payload["initial_state"]),
            snapshots=[ReplaySnapshot(**item) for item in payload["snapshots"]],
            event_stream=[ReplayEvent(**item) for item in payload["event_stream"]],
            highlights=list(payload["highlights"]),
            final_state=dict(payload["final_state"]),
        )


@dataclass
class BattleReportSummary:
    report_id: str
    replay_id: str
    scenario_name: str
    finished_at: str
    settlement_reason: str
    winner_side: str
    result_label: str
    duration_seconds: float
    replay_path: str
    has_replay: bool
    side_summary: dict[str, SideSummary]
    unit_rows: list[UnitBattleRow]
    highlights: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BattleReportSummary:
        return cls(
            report_id=payload["report_id"],
            replay_id=payload["replay_id"],
            scenario_name=payload["scenario_name"],
            finished_at=payload["finished_at"],
            settlement_reason=payload["settlement_reason"],
            winner_side=payload["winner_side"],
            result_label=payload["result_label"],
            duration_seconds=float(payload["duration_seconds"]),
            replay_path=payload["replay_path"],
            has_replay=bool(payload["has_replay"]),
            side_summary={
                side: SideSummary(**summary)
                for side, summary in payload["side_summary"].items()
            },
            unit_rows=[UnitBattleRow(**row) for row in payload["unit_rows"]],
            highlights=list(payload["highlights"]),
        )
