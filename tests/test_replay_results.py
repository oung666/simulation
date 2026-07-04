from __future__ import annotations

from simulation.controllers.combat_controller import CombatController
from simulation.core.geo import LonLat
from simulation.core.scenario import CombatUnit, Scenario, UnitRoute
from simulation.core.weapon import FlyingWeapon
from simulation.replay.models import ReplayEvent
from simulation.replay.results import build_battle_report_summary


class DummyUnit:
    def __init__(
        self,
        unit_id: str,
        name: str,
        side: str,
        alive: bool,
        position: LonLat | None,
    ) -> None:
        self.unit_id = unit_id
        self.name = name
        self.side = side
        self.alive = alive
        self.position = position
        self.unit_type = "aircraft"
        self.class_name = "Fighter"
        self.target_id = ""


class DummyScenario:
    def __init__(self) -> None:
        self.name = "demo"
        self.units = [
            DummyUnit("blue-1", "Blue One", "blue", True, LonLat(120.0, 24.0)),
            DummyUnit("red-1", "Red One", "red", False, LonLat(121.0, 25.0)),
        ]


def _build_unit(
    unit_id: str,
    name: str,
    side: str,
    position: LonLat,
    alive: bool = True,
) -> CombatUnit:
    return CombatUnit(
        unit_id=unit_id,
        name=name,
        side=side,
        unit_type="aircraft",
        route=UnitRoute([]),
        route_id="",
        motion="static",
        position=position,
        speed=0.0,
        range_nm=100.0,
        detection_range_nm=0.0,
        weapons=[],
        alive=alive,
        class_name="Fighter",
    )


def test_build_battle_report_summary_attributes_hits_and_kills_from_weapon_events() -> None:
    scenario = DummyScenario()
    events = [
        ReplayEvent(
            time=1.0,
            event_type="launched",
            source_id="blue-1",
            target_id="red-1",
            weapon_class="AIM-120D",
            position=None,
            message="launch",
            extra={},
        ),
        ReplayEvent(
            time=2.0,
            event_type="hit",
            source_id="weapon-1",
            target_id="red-1",
            weapon_class="AIM-120D",
            position=None,
            message="hit",
            extra={"attacker_unit_id": "blue-1", "attacker_side": "blue"},
        ),
        ReplayEvent(
            time=2.1,
            event_type="unit_destroyed",
            source_id="weapon-1",
            target_id="red-1",
            weapon_class="AIM-120D",
            position=None,
            message="destroyed",
            extra={"attacker_unit_id": "blue-1", "attacker_side": "blue"},
        ),
    ]

    summary = build_battle_report_summary(
        scenario=scenario,
        replay_id="replay-1",
        finished_at="2026-06-30T11:10:00",
        duration_seconds=600.0,
        settlement_reason="simulation_finished",
        events=events,
    )

    blue_row = next(row for row in summary.unit_rows if row.unit_id == "blue-1")
    red_row = next(row for row in summary.unit_rows if row.unit_id == "red-1")

    assert summary.winner_side == "blue"
    assert summary.result_label == "蓝方胜利"
    assert summary.replay_path == "replays/replay-1.json"
    assert summary.has_replay is True
    assert summary.side_summary["blue"].alive_count == 1
    assert summary.side_summary["blue"].launch_count == 1
    assert summary.side_summary["blue"].hit_count == 1
    assert summary.side_summary["blue"].kill_count == 1
    assert summary.side_summary["red"].lost_count == 1
    assert blue_row.launches == 1
    assert blue_row.hits == 1
    assert blue_row.kills == 1
    assert blue_row.alive is True
    assert blue_row.last_position == {"lon": 120.0, "lat": 24.0}
    assert red_row.destroyed is True
    assert red_row.final_mission_status == "destroyed"


def test_build_battle_report_summary_uses_destroyed_events_when_scenario_state_lags() -> None:
    scenario = DummyScenario()
    scenario.units[1].alive = True
    events = [
        ReplayEvent(
            time=2.0,
            event_type="unit_destroyed",
            source_id="weapon-1",
            target_id="red-1",
            weapon_class="AIM-120D",
            position=None,
            message="destroyed",
            extra={"attacker_unit_id": "blue-1", "attacker_side": "blue"},
        )
    ]

    summary = build_battle_report_summary(
        scenario=scenario,
        replay_id="replay-2",
        finished_at="2026-06-30T11:20:00",
        duration_seconds=620.0,
        settlement_reason="simulation_finished",
        events=events,
    )

    red_row = next(row for row in summary.unit_rows if row.unit_id == "red-1")

    assert summary.winner_side == "blue"
    assert summary.side_summary["blue"].alive_count == 1
    assert summary.side_summary["red"].alive_count == 0
    assert summary.side_summary["red"].lost_count == 1
    assert red_row.alive is False
    assert red_row.destroyed is True
    assert red_row.final_mission_status == "destroyed"


def test_combat_controller_emits_structured_destroy_event_for_weapon_hit() -> None:
    blue_position = LonLat(120.0, 24.0)
    red_position = LonLat(121.0, 25.0)
    shooter = _build_unit("blue-1", "Blue One", "blue", blue_position)
    target = _build_unit("red-1", "Red One", "red", red_position)
    scenario = Scenario(
        name="demo",
        units=[shooter, target],
        flying_weapons=[
            FlyingWeapon(
                weapon_id="weapon-1",
                name="AIM-120D #1",
                side="blue",
                weapon_class="AIM-120D",
                position=red_position,
                heading=0.0,
                speed=1200.0,
                target_id="red-1",
                lethality=1.0,
                fuel_remaining_s=30.0,
            )
        ],
    )
    controller = CombatController(scenario)

    controller.step(
        {
            "blue-1": blue_position,
            "red-1": red_position,
        },
        simulation_time=12.0,
    )

    hit_event = next(event for event in controller.combat_log if event.event_type == "hit")
    destroyed_event = next(event for event in controller.combat_log if event.event_type == "unit_destroyed")

    assert hit_event.source_id == "weapon-1"
    assert hit_event.extra["attacker_unit_id"] == "blue-1"
    assert hit_event.extra["attacker_side"] == "blue"
    assert destroyed_event.source_id == "weapon-1"
    assert destroyed_event.target_id == "red-1"
    assert destroyed_event.extra["attacker_unit_id"] == "blue-1"
    assert destroyed_event.extra["attacker_side"] == "blue"
    assert target.alive is False


def test_combat_controller_preserves_weapon_attacker_id_for_preexisting_weapon() -> None:
    blue_position = LonLat(120.0, 24.0)
    blue_two_position = LonLat(120.5, 24.5)
    red_position = LonLat(121.0, 25.0)
    shooter = _build_unit("blue-1", "Blue One", "blue", blue_position)
    wingman = _build_unit("blue-2", "Blue Two", "blue", blue_two_position)
    target = _build_unit("red-1", "Red One", "red", red_position)
    weapon = FlyingWeapon(
        weapon_id="weapon-2",
        name="AIM-120D #2",
        side="blue",
        weapon_class="AIM-120D",
        position=red_position,
        heading=0.0,
        speed=1200.0,
        target_id="red-1",
        lethality=1.0,
        fuel_remaining_s=30.0,
    )
    weapon.attacker_unit_id = "blue-2"
    scenario = Scenario(
        name="demo",
        units=[shooter, wingman, target],
        flying_weapons=[weapon],
    )
    controller = CombatController(scenario)

    controller.step(
        {
            "blue-1": blue_position,
            "blue-2": blue_two_position,
            "red-1": red_position,
        },
        simulation_time=14.0,
    )

    hit_event = next(event for event in controller.combat_log if event.event_type == "hit")
    destroyed_event = next(event for event in controller.combat_log if event.event_type == "unit_destroyed")

    assert hit_event.extra["attacker_unit_id"] == "blue-2"
    assert hit_event.extra["attacker_side"] == "blue"
    assert destroyed_event.extra["attacker_unit_id"] == "blue-2"
    assert destroyed_event.extra["attacker_side"] == "blue"
