from __future__ import annotations

from simulation.replay.recorder import ReplayRecorder


def test_recorder_captures_periodic_snapshots_and_events() -> None:
    recorder = ReplayRecorder(snapshot_interval_seconds=2.5)

    recorder.start(
        replay_id="r1",
        scenario_name="demo",
        started_at="2026-06-30T11:00:00",
        initial_state={
            "units": [{"unit_id": "blue-1", "alive": True}],
            "flying_weapons": [],
            "missions": [],
            "contacts": [],
        },
    )

    recorder.capture_periodic_snapshot(
        1.0,
        {
            "units": [{"unit_id": "blue-1", "alive": True}],
            "flying_weapons": [],
            "missions": [],
            "contacts": [],
        },
    )
    recorder.capture_periodic_snapshot(
        2.5,
        {
            "units": [{"unit_id": "blue-1", "alive": True}],
            "flying_weapons": [],
            "missions": [],
            "contacts": [],
        },
    )
    recorder.record_event(
        time=3.0,
        event_type="launched",
        source_id="blue-1",
        target_id="red-1",
        weapon_class="AIM-120D",
        position=None,
        message="launch",
    )

    replay = recorder.finish(
        ended_at="2026-06-30T11:10:00",
        duration_seconds=600.0,
        final_state={"alive": {"blue": 1, "red": 0}},
        settlement_reason="simulation_finished",
    )

    assert [snapshot.time for snapshot in replay.snapshots] == [0.0, 2.5]
    assert replay.snapshots[0].unit_states == [{"unit_id": "blue-1", "alive": True}]
    assert len(replay.event_stream) == 1
    assert replay.event_stream[0].event_type == "launched"
    assert replay.event_stream[0].source_id == "blue-1"
    assert replay.snapshot_interval_seconds == 2.5


def test_recorder_forced_snapshot_does_not_depend_on_periodic_interval() -> None:
    recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
    state = {
        "units": [{"unit_id": "blue-1", "alive": True}],
        "flying_weapons": [],
        "missions": [],
        "contacts": [],
    }

    recorder.start(
        replay_id="r2",
        scenario_name="demo",
        started_at="2026-06-30T11:00:00",
        initial_state=state,
    )
    recorder.record_event(
        time=0.8,
        event_type="detected",
        source_id="blue-1",
        target_id="red-1",
        weapon_class="",
        position=None,
        message="detect",
        force_snapshot_state=state,
    )

    state["units"][0]["alive"] = False

    replay = recorder.finish(
        ended_at="2026-06-30T11:01:00",
        duration_seconds=60.0,
        final_state={"alive": {"blue": 1, "red": 1}},
        settlement_reason="manual_settlement",
    )

    assert [snapshot.time for snapshot in replay.snapshots] == [0.0, 0.8]
    assert replay.snapshots[1].unit_states == [{"unit_id": "blue-1", "alive": True}]


def test_recorder_finish_can_append_final_snapshot() -> None:
    recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
    final_snapshot_state = {
        "units": [{"unit_id": "blue-1", "alive": False}],
        "flying_weapons": [],
        "missions": [],
        "contacts": [],
    }

    recorder.start(
        replay_id="r3",
        scenario_name="demo",
        started_at="2026-06-30T11:00:00",
        initial_state={
            "units": [{"unit_id": "blue-1", "alive": True}],
            "flying_weapons": [],
            "missions": [],
            "contacts": [],
        },
    )

    replay = recorder.finish(
        ended_at="2026-06-30T11:01:00",
        duration_seconds=60.0,
        final_state={"alive": {"blue": 0, "red": 1}},
        settlement_reason="simulation_finished",
        final_snapshot_state=final_snapshot_state,
    )

    assert [snapshot.time for snapshot in replay.snapshots] == [0.0, 60.0]
    assert replay.snapshots[-1].unit_states == [{"unit_id": "blue-1", "alive": False}]


def test_recorder_uses_recording_relative_time_when_started_mid_simulation() -> None:
    recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
    state = {
        "units": [{"unit_id": "blue-1", "alive": True}],
        "flying_weapons": [],
        "missions": [],
        "contacts": [],
    }

    recorder.start(
        replay_id="r-mid",
        scenario_name="demo",
        started_at="2026-06-30T11:00:00",
        initial_state=state,
        initial_time=120.0,
    )
    recorder.capture_periodic_snapshot(122.5, state)
    recorder.record_event(
        time=123.0,
        event_type="detected",
        source_id="blue-1",
        target_id="red-1",
        weapon_class="",
        position=None,
        message="detect",
        force_snapshot_state=state,
    )

    replay = recorder.finish(
        ended_at="2026-06-30T11:01:00",
        duration_seconds=125.0,
        final_state={"alive": {"blue": 1, "red": 1}},
        settlement_reason="manual_settlement",
        final_snapshot_state=state,
    )

    assert replay.duration_seconds == 5.0
    assert [snapshot.time for snapshot in replay.snapshots] == [0.0, 2.5, 3.0, 5.0]
    assert replay.event_stream[0].time == 3.0


def test_recorder_event_position_is_not_mutated_by_later_changes() -> None:
    recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
    position = {"lon": 120.0, "lat": 24.0}

    recorder.start(
        replay_id="r4",
        scenario_name="demo",
        started_at="2026-06-30T11:00:00",
        initial_state={
            "units": [],
            "flying_weapons": [],
            "missions": [],
            "contacts": [],
        },
    )
    recorder.record_event(
        time=1.0,
        event_type="hit",
        source_id="blue-1",
        target_id="red-1",
        weapon_class="AIM-120D",
        position=position,
        message="hit",
    )

    position["lon"] = 121.0

    replay = recorder.finish(
        ended_at="2026-06-30T11:01:00",
        duration_seconds=60.0,
        final_state={"alive": {"blue": 1, "red": 0}},
        settlement_reason="simulation_finished",
    )

    assert replay.event_stream[0].position == {"lon": 120.0, "lat": 24.0}
