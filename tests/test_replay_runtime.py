from simulation.replay.models import ReplayEvent, ReplayRecord, ReplaySnapshot
from simulation.replay.runtime import ReplayRuntime


def test_replay_runtime_restores_snapshot_and_applies_events() -> None:
    replay = ReplayRecord(
        replay_id="r1",
        scenario_name="demo",
        started_at="2026-06-30T10:00:00",
        ended_at="2026-06-30T10:10:00",
        settlement_reason="simulation_finished",
        duration_seconds=600.0,
        tick_interval_seconds=1.0,
        snapshot_interval_seconds=2.5,
        participants=["blue", "red"],
        initial_state={"units": []},
        snapshots=[
            ReplaySnapshot(
                time=0.0,
                clock_state={"current_time": 0.0},
                unit_states=[{"unit_id": "blue-1", "alive": True}],
                flying_weapon_states=[],
                mission_states=[],
                contact_track_states=[],
            ),
            ReplaySnapshot(
                time=2.5,
                clock_state={"current_time": 2.5},
                unit_states=[{"unit_id": "blue-1", "alive": True}],
                flying_weapon_states=[],
                mission_states=[],
                contact_track_states=[],
            ),
        ],
        event_stream=[
            ReplayEvent(
                time=3.0,
                event_type="unit_destroyed",
                source_id="red-1",
                target_id="blue-1",
                weapon_class="",
                position=None,
                message="destroy",
                extra={},
            )
        ],
        highlights=[],
        final_state={"alive": {"blue": 0, "red": 1}},
    )
    runtime = ReplayRuntime(replay)
    state = runtime.seek(3.0)

    assert state["current_time"] == 3.0
    assert state["units"][0]["alive"] is False
