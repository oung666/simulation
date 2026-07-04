from __future__ import annotations

import json
from pathlib import Path

from simulation.replay.models import (
    BattleReportSummary,
    ReplayEvent,
    ReplayRecord,
    ReplaySnapshot,
    SideSummary,
    UnitBattleRow,
)
from simulation.replay.storage import ReplayStorage


def _build_replay(replay_id: str) -> ReplayRecord:
    return ReplayRecord(
        replay_id=replay_id,
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
                unit_states=[],
                flying_weapon_states=[],
                mission_states=[],
                contact_track_states=[],
            )
        ],
        event_stream=[
            ReplayEvent(
                time=5.0,
                event_type="launched",
                source_id="blue-1",
                target_id="red-1",
                weapon_class="AIM-120D",
                position=None,
                message="launch",
                extra={},
            )
        ],
        highlights=[{"time": 5.0, "label": "首发"}],
        final_state={"alive": {"blue": 1, "red": 0}},
    )


def _build_summary(report_id: str, replay_id: str, finished_at: str) -> BattleReportSummary:
    return BattleReportSummary(
        report_id=report_id,
        replay_id=replay_id,
        scenario_name="demo",
        finished_at=finished_at,
        settlement_reason="simulation_finished",
        winner_side="blue",
        result_label="blue_win",
        duration_seconds=600.0,
        replay_path=f"replays/{replay_id}.json",
        has_replay=True,
        side_summary={
            "blue": SideSummary(
                alive_count=1,
                lost_count=0,
                launch_count=1,
                hit_count=1,
                kill_count=1,
            ),
            "red": SideSummary(
                alive_count=0,
                lost_count=1,
                launch_count=0,
                hit_count=0,
                kill_count=0,
            ),
        },
        unit_rows=[
            UnitBattleRow(
                unit_id="blue-1",
                name="Blue One",
                side="blue",
                unit_type="aircraft",
                class_name="F-35A Lightning II",
                alive=True,
                kills=1,
                destroyed=False,
                launches=1,
                hits=1,
                last_position={"lon": 120.0, "lat": 24.0},
                final_mission_status="active",
            )
        ],
        highlights=[{"time": 5.0, "label": "首发"}],
    )


def test_replay_storage_roundtrip(tmp_path: Path) -> None:
    storage = ReplayStorage(tmp_path / "replays", tmp_path / "battle_reports")
    replay = _build_replay("replay-1")
    summary = _build_summary(
        report_id="report-1",
        replay_id="replay-1",
        finished_at="2026-06-30T10:10:00",
    )

    replay_path = storage.save_replay(replay)
    report_path = storage.save_report(summary)

    loaded_replay = storage.load_replay("replay-1")
    loaded_reports = storage.list_reports()

    replay_payload = json.loads(replay_path.read_text(encoding="utf-8"))
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert replay_path.name == "replay-1.json"
    assert report_path.name == "report-1.json"
    assert replay_payload["highlights"][0]["label"] == "首发"
    assert report_payload["highlights"][0]["label"] == "首发"
    assert loaded_replay == replay
    assert len(loaded_reports) == 1
    assert loaded_reports[0] == summary


def test_replay_storage_lists_reports_by_finished_at_descending(tmp_path: Path) -> None:
    storage = ReplayStorage(tmp_path / "replays", tmp_path / "battle_reports")

    older = _build_summary(
        report_id="report-z",
        replay_id="replay-z",
        finished_at="2026-06-30T10:00:00",
    )
    newer = _build_summary(
        report_id="report-a",
        replay_id="replay-a",
        finished_at="2026-06-30T11:00:00",
    )

    storage.save_report(older)
    storage.save_report(newer)

    reports = storage.list_reports()

    assert [report.report_id for report in reports] == ["report-a", "report-z"]


def test_replay_storage_can_delete_report_only(tmp_path: Path) -> None:
    storage = ReplayStorage(tmp_path / "replays", tmp_path / "battle_reports")
    replay = _build_replay("replay-1")
    summary = _build_summary("report-1", "replay-1", "2026-06-30T10:10:00")

    storage.save_replay(replay)
    storage.save_report(summary)

    storage.delete_report_only("report-1")

    assert (tmp_path / "battle_reports" / "report-1.json").exists() is False
    assert (tmp_path / "replays" / "replay-1.json").exists() is True


def test_replay_storage_can_delete_report_and_replay(tmp_path: Path) -> None:
    storage = ReplayStorage(tmp_path / "replays", tmp_path / "battle_reports")
    replay = _build_replay("replay-1")
    summary = _build_summary("report-1", "replay-1", "2026-06-30T10:10:00")

    storage.save_replay(replay)
    storage.save_report(summary)

    storage.delete_report_and_replay("report-1", "replay-1")

    assert (tmp_path / "battle_reports" / "report-1.json").exists() is False
    assert (tmp_path / "replays" / "replay-1.json").exists() is False
