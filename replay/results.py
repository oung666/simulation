from __future__ import annotations

from collections import defaultdict

from simulation.replay.models import BattleReportSummary, ReplayEvent, SideSummary, UnitBattleRow


def build_battle_report_summary(
    scenario,
    replay_id: str,
    finished_at: str,
    duration_seconds: float,
    settlement_reason: str,
    events: list[ReplayEvent],
) -> BattleReportSummary:
    units_by_id = {unit.unit_id: unit for unit in scenario.units}
    side_stats = {
        side: {"alive": 0, "lost": 0, "launch": 0, "hit": 0, "kill": 0}
        for side in {unit.side for unit in scenario.units}
    }
    per_unit_launches: dict[str, int] = defaultdict(int)
    per_unit_hits: dict[str, int] = defaultdict(int)
    per_unit_kills: dict[str, int] = defaultdict(int)
    destroyed_units = {event.target_id for event in events if event.event_type == "unit_destroyed"}

    def ensure_side(side: str) -> None:
        side_stats.setdefault(side, {"alive": 0, "lost": 0, "launch": 0, "hit": 0, "kill": 0})

    def attacker_unit_id_for(event: ReplayEvent) -> str:
        attacker_unit_id = str(event.extra.get("attacker_unit_id", "")).strip()
        if attacker_unit_id in units_by_id:
            return attacker_unit_id
        if event.source_id in units_by_id:
            return event.source_id
        return ""

    def attacker_side_for(event: ReplayEvent) -> str:
        attacker_unit_id = attacker_unit_id_for(event)
        if attacker_unit_id:
            return units_by_id[attacker_unit_id].side
        return str(event.extra.get("attacker_side", "")).strip()

    for event in events:
        attacker_unit_id = attacker_unit_id_for(event)
        attacker_side = attacker_side_for(event)
        if attacker_side:
            ensure_side(attacker_side)

        if event.event_type == "launched" and attacker_unit_id:
            side_stats[units_by_id[attacker_unit_id].side]["launch"] += 1
            per_unit_launches[attacker_unit_id] += 1
        elif event.event_type == "hit":
            if attacker_side:
                side_stats[attacker_side]["hit"] += 1
            if attacker_unit_id:
                per_unit_hits[attacker_unit_id] += 1
        elif event.event_type == "unit_destroyed":
            if attacker_side:
                side_stats[attacker_side]["kill"] += 1
            if attacker_unit_id:
                per_unit_kills[attacker_unit_id] += 1

    effective_alive_by_unit_id = {
        unit_id: unit_id not in destroyed_units and bool(getattr(unit, "alive", False))
        for unit_id, unit in units_by_id.items()
    }

    unit_rows: list[UnitBattleRow] = []
    for unit in scenario.units:
        ensure_side(unit.side)
        effective_alive = effective_alive_by_unit_id[unit.unit_id]
        if effective_alive:
            side_stats[unit.side]["alive"] += 1
        else:
            side_stats[unit.side]["lost"] += 1

        last_position = None
        if unit.position is not None:
            last_position = {"lon": float(unit.position.lon), "lat": float(unit.position.lat)}

        unit_rows.append(
            UnitBattleRow(
                unit_id=unit.unit_id,
                name=unit.name,
                side=unit.side,
                unit_type=unit.unit_type,
                class_name=str(getattr(unit, "class_name", "")),
                alive=effective_alive,
                kills=per_unit_kills[unit.unit_id],
                destroyed=not effective_alive,
                launches=per_unit_launches[unit.unit_id],
                hits=per_unit_hits[unit.unit_id],
                last_position=last_position,
                final_mission_status="active" if effective_alive else "destroyed",
            )
        )

    winner_side = "draw"
    alive_counts = {side: stats["alive"] for side, stats in side_stats.items()}
    if alive_counts:
        max_alive = max(alive_counts.values())
        winners = [side for side, alive_count in alive_counts.items() if alive_count == max_alive]
        if len(winners) == 1:
            winner_side = winners[0]

    result_label = {
        "blue": "蓝方胜利",
        "red": "红方胜利",
        "draw": "平局",
    }[winner_side]
    return BattleReportSummary(
        report_id=f"report-{replay_id}",
        replay_id=replay_id,
        scenario_name=scenario.name,
        finished_at=finished_at,
        settlement_reason=settlement_reason,
        winner_side=winner_side,
        result_label=result_label,
        duration_seconds=duration_seconds,
        replay_path=f"replays/{replay_id}.json",
        has_replay=True,
        side_summary={
            side: SideSummary(
                alive_count=stats["alive"],
                lost_count=stats["lost"],
                launch_count=stats["launch"],
                hit_count=stats["hit"],
                kill_count=stats["kill"],
            )
            for side, stats in side_stats.items()
        },
        unit_rows=unit_rows,
        highlights=[],
    )
