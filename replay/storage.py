from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from simulation.replay.models import BattleReportSummary, ReplayRecord


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


class ReplayStorage:
    def __init__(self, replay_dir: Path, report_dir: Path) -> None:
        self.replay_dir = replay_dir
        self.report_dir = report_dir
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def save_replay(self, replay: ReplayRecord) -> Path:
        path = self.replay_dir / f"{replay.replay_id}.json"
        _write_json(path, replay.to_dict())
        return path

    def save_report(self, summary: BattleReportSummary) -> Path:
        path = self.report_dir / f"{summary.report_id}.json"
        _write_json(path, summary.to_dict())
        return path

    def load_replay(self, replay_id: str) -> ReplayRecord:
        path = self.replay_dir / f"{replay_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ReplayRecord.from_dict(payload)

    def load_report(self, report_id: str) -> BattleReportSummary:
        path = self.report_dir / f"{report_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return BattleReportSummary.from_dict(payload)

    def list_reports(self) -> list[BattleReportSummary]:
        reports: list[BattleReportSummary] = []
        for path in self.report_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            reports.append(BattleReportSummary.from_dict(payload))
        reports.sort(key=lambda report: report.finished_at, reverse=True)
        return reports

    def delete_report_only(self, report_id: str) -> None:
        path = self.report_dir / f"{report_id}.json"
        if path.exists():
            path.unlink()

    def delete_report_and_replay(self, report_id: str, replay_id: str) -> None:
        self.delete_report_only(report_id)
        replay_path = self.replay_dir / f"{replay_id}.json"
        if replay_path.exists():
            replay_path.unlink()
