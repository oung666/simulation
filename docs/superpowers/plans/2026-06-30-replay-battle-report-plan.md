# 回放录制与战绩系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前仿真项目增加一套轻量但完整的回放录制、战绩结算、历史战绩浏览与回放查看能力，并支持战绩记录和回放文件的分级清理。

**Architecture:** 方案采用“快照 + 事件流”的标准回放结构。实时仿真继续由 `MainWindow + MapCanvas + CombatController` 驱动，新增的录制、战绩统计、持久化、回放运行时和回放界面全部拆到独立模块中，只通过清晰的接入点和现有主界面连接。

**Tech Stack:** Python 3.11、PyQt5、现有 `simulation` 数据模型、JSON 持久化、`pytest` 用于新增单元测试、现有 `smoke_qt.py` 和 `validate_project.py` 用于集成验证。

---

## 文件结构与职责

### 新增文件

- `D:\project-simulation\simulation\replay\__init__.py`
  - 回放子包导出入口
- `D:\project-simulation\simulation\replay\models.py`
  - 回放快照、事件、战绩摘要等 dataclass
- `D:\project-simulation\simulation\replay\storage.py`
  - 回放文件与战绩摘要的保存、加载、删除、索引查询
- `D:\project-simulation\simulation\replay\recorder.py`
  - 录制会话、2.5 秒快照、关键事件补快照、结算封存
- `D:\project-simulation\simulation\replay\results.py`
  - 从 `Scenario + CombatEvent` 生成阵营总览、单位战绩、关键事件摘要
- `D:\project-simulation\simulation\replay\runtime.py`
  - 回放状态恢复、按时间推进、关键事件跳转
- `D:\project-simulation\simulation\ui\battle_report_dialog.py`
  - 战绩列表与赛后页对话框
- `D:\project-simulation\simulation\ui\replay_viewer_dialog.py`
  - 回放播放对话框
- `D:\project-simulation\simulation\tests\test_replay_storage.py`
  - 存储层测试
- `D:\project-simulation\simulation\tests\test_replay_recorder.py`
  - 录制器测试
- `D:\project-simulation\simulation\tests\test_replay_results.py`
  - 战绩统计测试

### 修改文件

- `D:\project-simulation\simulation\controllers\combat_controller.py`
  - 补充结构化事件字段，便于录制和战绩统计复用
- `D:\project-simulation\simulation\ui\map_canvas.py`
  - 增加录制器接入点，不改变其实时主职责
- `D:\project-simulation\simulation\ui\main_window.py`
  - 工具栏新增 `录制 / 结算 / 战绩`，并串起录制和战绩入口
- `D:\project-simulation\simulation\tools\smoke_qt.py`
  - 增加录制、战绩对话框、清理动作的基础 smoke 验证

### 现有辅助文件

- `D:\project-simulation\simulation\tools\validate_project.py`
  - 本次原则上不扩展复杂逻辑，只在必要时追加最轻量回放目录校验

## 任务拆解

### Task 1: 建立回放数据模型与存储层

**Files:**
- Create: `D:\project-simulation\simulation\replay\__init__.py`
- Create: `D:\project-simulation\simulation\replay\models.py`
- Create: `D:\project-simulation\simulation\replay\storage.py`
- Create: `D:\project-simulation\simulation\tests\test_replay_storage.py`

- [ ] **Step 1: 先写存储层失败测试**

```python
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


def test_replay_storage_roundtrip(tmp_path: Path) -> None:
    storage = ReplayStorage(tmp_path / "replays", tmp_path / "battle_reports")
    replay = ReplayRecord(
        replay_id="replay-1",
        scenario_name="demo",
        started_at="2026-06-30T10:00:00",
        ended_at="2026-06-30T10:10:00",
        settlement_reason="simulation_finished",
        duration_seconds=600.0,
        tick_interval_seconds=1.0,
        snapshot_interval_seconds=2.5,
        participants=["blue", "red"],
        initial_state={"units": []},
        snapshots=[ReplaySnapshot(time=0.0, clock_state={"current_time": 0.0}, unit_states=[], flying_weapon_states=[], mission_states=[], contact_track_states=[])],
        event_stream=[ReplayEvent(time=5.0, event_type="launched", source_id="blue-1", target_id="red-1", weapon_class="AIM-120D", position=None, message="launch", extra={})],
        highlights=[],
        final_state={"alive": {"blue": 1, "red": 0}},
    )
    summary = BattleReportSummary(
        report_id="report-1",
        replay_id="replay-1",
        scenario_name="demo",
        finished_at="2026-06-30T10:10:00",
        settlement_reason="simulation_finished",
        winner_side="blue",
        result_label="蓝方胜利",
        duration_seconds=600.0,
        replay_path="replays/replay-1.json",
        has_replay=True,
        side_summary={
            "blue": SideSummary(alive_count=1, lost_count=0, launch_count=1, hit_count=1, kill_count=1),
            "red": SideSummary(alive_count=0, lost_count=1, launch_count=0, hit_count=0, kill_count=0),
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
        highlights=[],
    )

    storage.save_replay(replay)
    storage.save_report(summary)

    loaded_replay = storage.load_replay("replay-1")
    loaded_reports = storage.list_reports()

    assert loaded_replay.replay_id == "replay-1"
    assert len(loaded_reports) == 1
    assert loaded_reports[0].report_id == "report-1"
```

- [ ] **Step 2: 运行测试并确认它先失败**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_storage.py -q`

Expected: FAIL，报 `ModuleNotFoundError: No module named 'simulation.replay'` 或找不到 `ReplayStorage`

- [ ] **Step 3: 写最小数据模型与存储实现**

`D:\project-simulation\simulation\replay\models.py`

```python
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
```

`D:\project-simulation\simulation\replay\storage.py`

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from simulation.replay.models import (
    BattleReportSummary,
    ReplayEvent,
    ReplayRecord,
    ReplaySnapshot,
    SideSummary,
    UnitBattleRow,
)


class ReplayStorage:
    def __init__(self, replay_dir: Path, report_dir: Path) -> None:
        self.replay_dir = replay_dir
        self.report_dir = report_dir
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def save_replay(self, replay: ReplayRecord) -> Path:
        path = self.replay_dir / f"{replay.replay_id}.json"
        path.write_text(json.dumps(replay.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def save_report(self, summary: BattleReportSummary) -> Path:
        path = self.report_dir / f"{summary.report_id}.json"
        path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def load_replay(self, replay_id: str) -> ReplayRecord:
        payload = json.loads((self.replay_dir / f"{replay_id}.json").read_text(encoding="utf-8"))
        return ReplayRecord(
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

    def list_reports(self) -> list[BattleReportSummary]:
        reports: list[BattleReportSummary] = []
        for path in sorted(self.report_dir.glob("*.json"), reverse=True):
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            reports.append(
                BattleReportSummary(
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
                    side_summary={side: SideSummary(**summary) for side, summary in payload["side_summary"].items()},
                    unit_rows=[UnitBattleRow(**row) for row in payload["unit_rows"]],
                    highlights=list(payload["highlights"]),
                )
            )
        return reports
```

`D:\project-simulation\simulation\replay\__init__.py`

```python
"""Replay recording, battle report, and playback support."""
```

- [ ] **Step 4: 再次运行测试，确认回合通过**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_storage.py -q`

Expected: PASS，输出 `1 passed`

- [ ] **Step 5: 提交或记录当前里程碑**

Current workspace note: `D:\project-simulation` 不是 git 仓库，`git status` 会失败，因此本计划在当前环境跳过 commit。

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

### Task 2: 实现录制器与 2.5 秒快照策略

**Files:**
- Create: `D:\project-simulation\simulation\replay\recorder.py`
- Create: `D:\project-simulation\simulation\tests\test_replay_recorder.py`
- Modify: `D:\project-simulation\simulation\replay\models.py`

- [ ] **Step 1: 先写录制器失败测试**

```python
from simulation.replay.recorder import ReplayRecorder


def test_recorder_captures_periodic_and_forced_snapshots() -> None:
    recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
    recorder.start(
        replay_id="r1",
        scenario_name="demo",
        started_at="2026-06-30T11:00:00",
        initial_state={"units": [{"unit_id": "blue-1"}]},
    )

    recorder.capture_periodic_snapshot(1.0, {"units": [{"unit_id": "blue-1", "alive": True}]})
    recorder.capture_periodic_snapshot(2.5, {"units": [{"unit_id": "blue-1", "alive": True}]})
    recorder.record_event(
        time=3.0,
        event_type="launched",
        source_id="blue-1",
        target_id="red-1",
        weapon_class="AIM-120D",
        position=None,
        message="launch",
        force_snapshot_state={"units": [{"unit_id": "blue-1", "alive": True}]},
    )

    replay = recorder.finish("2026-06-30T11:10:00", 600.0, {"alive": {"blue": 1, "red": 0}}, "simulation_finished")

    assert len(replay.snapshots) == 3
    assert replay.snapshots[1].time == 2.5
    assert replay.event_stream[0].event_type == "launched"
```

- [ ] **Step 2: 运行测试并确认先失败**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_recorder.py -q`

Expected: FAIL，报找不到 `ReplayRecorder`

- [ ] **Step 3: 写最小录制器实现**

`D:\project-simulation\simulation\replay\recorder.py`

```python
from __future__ import annotations

from dataclasses import replace

from simulation.replay.models import ReplayEvent, ReplayRecord, ReplaySnapshot


class ReplayRecorder:
    def __init__(self, snapshot_interval_seconds: float = 2.5) -> None:
        self.snapshot_interval_seconds = snapshot_interval_seconds
        self._active = False
        self._replay_id = ""
        self._scenario_name = ""
        self._started_at = ""
        self._initial_state = {}
        self._snapshots: list[ReplaySnapshot] = []
        self._events: list[ReplayEvent] = []
        self._last_periodic_snapshot_time = 0.0

    @property
    def active(self) -> bool:
        return self._active

    def start(self, replay_id: str, scenario_name: str, started_at: str, initial_state: dict) -> None:
        self._active = True
        self._replay_id = replay_id
        self._scenario_name = scenario_name
        self._started_at = started_at
        self._initial_state = dict(initial_state)
        self._snapshots = [self._snapshot_from_state(0.0, initial_state)]
        self._events = []
        self._last_periodic_snapshot_time = 0.0

    def capture_periodic_snapshot(self, time: float, state: dict) -> None:
        if not self._active:
            return
        if time - self._last_periodic_snapshot_time < self.snapshot_interval_seconds:
            return
        self._snapshots.append(self._snapshot_from_state(time, state))
        self._last_periodic_snapshot_time = time

    def record_event(
        self,
        time: float,
        event_type: str,
        source_id: str,
        target_id: str,
        weapon_class: str,
        position,
        message: str,
        force_snapshot_state: dict | None = None,
    ) -> None:
        if not self._active:
            return
        self._events.append(
            ReplayEvent(
                time=time,
                event_type=event_type,
                source_id=source_id,
                target_id=target_id,
                weapon_class=weapon_class,
                position=position,
                message=message,
                extra={},
            )
        )
        if force_snapshot_state is not None:
            self._snapshots.append(self._snapshot_from_state(time, force_snapshot_state))

    def finish(self, ended_at: str, duration_seconds: float, final_state: dict, settlement_reason: str) -> ReplayRecord:
        replay = ReplayRecord(
            replay_id=self._replay_id,
            scenario_name=self._scenario_name,
            started_at=self._started_at,
            ended_at=ended_at,
            settlement_reason=settlement_reason,
            duration_seconds=duration_seconds,
            tick_interval_seconds=1.0,
            snapshot_interval_seconds=self.snapshot_interval_seconds,
            participants=["blue", "red"],
            initial_state=dict(self._initial_state),
            snapshots=list(self._snapshots),
            event_stream=list(self._events),
            highlights=[],
            final_state=dict(final_state),
        )
        self._active = False
        return replay

    @staticmethod
    def _snapshot_from_state(time: float, state: dict) -> ReplaySnapshot:
        return ReplaySnapshot(
            time=time,
            clock_state={"current_time": time},
            unit_states=list(state.get("units", [])),
            flying_weapon_states=list(state.get("flying_weapons", [])),
            mission_states=list(state.get("missions", [])),
            contact_track_states=list(state.get("contacts", [])),
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_recorder.py -q`

Expected: PASS，输出 `1 passed`

- [ ] **Step 5: 补一个“关键事件强制快照”边界测试**

```python
def test_recorder_forced_snapshot_does_not_depend_on_periodic_interval() -> None:
    recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
    recorder.start("r2", "demo", "2026-06-30T11:00:00", {"units": []})

    recorder.record_event(
        time=0.8,
        event_type="detected",
        source_id="blue-1",
        target_id="red-1",
        weapon_class="",
        position=None,
        message="detect",
        force_snapshot_state={"units": [{"unit_id": "blue-1"}]},
    )

    replay = recorder.finish("2026-06-30T11:01:00", 60.0, {"alive": {"blue": 1, "red": 1}}, "manual_settlement")

    assert [snapshot.time for snapshot in replay.snapshots] == [0.0, 0.8]
```

- [ ] **Step 6: 当前环境同样跳过 commit**

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

### Task 3: 实现战绩统计构建器

**Files:**
- Create: `D:\project-simulation\simulation\replay\results.py`
- Create: `D:\project-simulation\simulation\tests\test_replay_results.py`
- Modify: `D:\project-simulation\simulation\controllers\combat_controller.py`

- [ ] **Step 1: 先写战绩统计失败测试**

```python
from simulation.replay.models import ReplayEvent
from simulation.replay.results import build_battle_report_summary


class DummyUnit:
    def __init__(self, unit_id: str, name: str, side: str, alive: bool) -> None:
        self.unit_id = unit_id
        self.name = name
        self.side = side
        self.alive = alive
        self.unit_type = "aircraft"
        self.class_name = "F-35A Lightning II"
        self.position = None


class DummyScenario:
    def __init__(self) -> None:
        self.name = "demo"
        self.units = [
            DummyUnit("blue-1", "Blue One", "blue", True),
            DummyUnit("red-1", "Red One", "red", False),
        ]


def test_build_battle_report_summary_counts_launches_hits_and_losses() -> None:
    scenario = DummyScenario()
    events = [
        ReplayEvent(time=1.0, event_type="launched", source_id="blue-1", target_id="red-1", weapon_class="AIM-120D", position=None, message="launch", extra={}),
        ReplayEvent(time=2.0, event_type="hit", source_id="blue-1", target_id="red-1", weapon_class="AIM-120D", position=None, message="hit", extra={}),
        ReplayEvent(time=2.1, event_type="unit_destroyed", source_id="blue-1", target_id="red-1", weapon_class="", position=None, message="destroyed", extra={}),
    ]

    summary = build_battle_report_summary(
        scenario=scenario,
        replay_id="replay-1",
        finished_at="2026-06-30T11:10:00",
        duration_seconds=600.0,
        settlement_reason="simulation_finished",
        events=events,
    )

    assert summary.winner_side == "blue"
    assert summary.side_summary["blue"].launch_count == 1
    assert summary.side_summary["blue"].hit_count == 1
    assert summary.side_summary["red"].lost_count == 1
    assert summary.unit_rows[0].unit_id == "blue-1"
```

- [ ] **Step 2: 运行测试确认它失败**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_results.py -q`

Expected: FAIL，报找不到 `build_battle_report_summary`

- [ ] **Step 3: 写最小战绩汇总实现**

`D:\project-simulation\simulation\replay\results.py`

```python
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from simulation.replay.models import BattleReportSummary, ReplayEvent, SideSummary, UnitBattleRow


def build_battle_report_summary(
    scenario,
    replay_id: str,
    finished_at: str,
    duration_seconds: float,
    settlement_reason: str,
    events: list[ReplayEvent],
) -> BattleReportSummary:
    side_stats = {
        "blue": {"alive": 0, "lost": 0, "launch": 0, "hit": 0, "kill": 0},
        "red": {"alive": 0, "lost": 0, "launch": 0, "hit": 0, "kill": 0},
    }
    per_unit_launches = defaultdict(int)
    per_unit_hits = defaultdict(int)
    per_unit_kills = defaultdict(int)
    destroyed_units = {event.target_id for event in events if event.event_type == "unit_destroyed"}

    units_by_id = {unit.unit_id: unit for unit in scenario.units}
    for event in events:
        source = units_by_id.get(event.source_id)
        target = units_by_id.get(event.target_id)
        if event.event_type == "launched" and source is not None:
            side_stats[source.side]["launch"] += 1
            per_unit_launches[source.unit_id] += 1
        if event.event_type == "hit" and source is not None:
            side_stats[source.side]["hit"] += 1
            per_unit_hits[source.unit_id] += 1
        if event.event_type == "unit_destroyed" and source is not None and target is not None:
            side_stats[source.side]["kill"] += 1
            per_unit_kills[source.unit_id] += 1

    rows: list[UnitBattleRow] = []
    for unit in scenario.units:
        if unit.alive:
            side_stats[unit.side]["alive"] += 1
        else:
            side_stats[unit.side]["lost"] += 1
        position = None if unit.position is None else {"lon": unit.position.lon, "lat": unit.position.lat}
        rows.append(
            UnitBattleRow(
                unit_id=unit.unit_id,
                name=unit.name,
                side=unit.side,
                unit_type=unit.unit_type,
                class_name=getattr(unit, "class_name", ""),
                alive=unit.alive,
                kills=per_unit_kills[unit.unit_id],
                destroyed=unit.unit_id in destroyed_units or not unit.alive,
                launches=per_unit_launches[unit.unit_id],
                hits=per_unit_hits[unit.unit_id],
                last_position=position,
                final_mission_status="active" if unit.alive else "destroyed",
            )
        )

    winner_side = "draw"
    if side_stats["blue"]["alive"] > side_stats["red"]["alive"]:
        winner_side = "blue"
    elif side_stats["red"]["alive"] > side_stats["blue"]["alive"]:
        winner_side = "red"

    result_label = {"blue": "蓝方胜利", "red": "红方胜利", "draw": "平局"}[winner_side]
    report_id = f"report-{replay_id}"
    return BattleReportSummary(
        report_id=report_id,
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
            "blue": SideSummary(
                alive_count=side_stats["blue"]["alive"],
                lost_count=side_stats["blue"]["lost"],
                launch_count=side_stats["blue"]["launch"],
                hit_count=side_stats["blue"]["hit"],
                kill_count=side_stats["blue"]["kill"],
            ),
            "red": SideSummary(
                alive_count=side_stats["red"]["alive"],
                lost_count=side_stats["red"]["lost"],
                launch_count=side_stats["red"]["launch"],
                hit_count=side_stats["red"]["hit"],
                kill_count=side_stats["red"]["kill"],
            ),
        },
        unit_rows=rows,
        highlights=[],
    )
```

- [ ] **Step 4: 补结构化销毁事件输出**

在 `D:\project-simulation\simulation\controllers\combat_controller.py` 的命中结果处理附近增加一条结构化销毁事件。最小修改方向如下：

```python
if result == "hit":
    self._add_event(
        "hit",
        weapon.weapon_id,
        weapon.target_id,
        weapon.weapon_class,
        f"{weapon.name} ...",
        target.position if target else weapon.position,
    )
    if target is not None and not target.alive:
        self._add_event(
            "unit_destroyed",
            weapon.weapon_id,
            target.unit_id,
            weapon.weapon_class,
            f"{target.name} 被摧毁",
            target.position,
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_results.py -q`

Expected: PASS，输出 `1 passed`

- [ ] **Step 6: 当前环境跳过 commit**

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

### Task 4: 将录制器接入实时仿真与结算流程

**Files:**
- Modify: `D:\project-simulation\simulation\ui\main_window.py`
- Modify: `D:\project-simulation\simulation\ui\map_canvas.py`
- Modify: `D:\project-simulation\simulation\replay\recorder.py`
- Modify: `D:\project-simulation\simulation\replay\storage.py`
- Modify: `D:\project-simulation\simulation\replay\results.py`

- [ ] **Step 1: 先写一个最小集成测试或 smoke 目标**

在 `D:\project-simulation\simulation\tools\smoke_qt.py` 先增加一个失败断言，目标是“开启录制后手动结算会产生至少一条战绩记录”：

```python
def _check_manual_settlement_creates_report(window: MainWindow) -> None:
    window._set_recording_enabled(True)
    window._settle_recorded_run()
    assert len(window._battle_reports_cache) >= 1
```

- [ ] **Step 2: 运行 smoke 并确认这条能力当前缺失**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\smoke_qt.py`

Expected: FAIL，报 `MainWindow` 中缺少录制开关或战绩缓存字段

- [ ] **Step 3: 在 MainWindow 初始化录制与存储依赖**

在 `D:\project-simulation\simulation\ui\main_window.py` 的 `__init__` 中新增：

```python
from datetime import datetime
from pathlib import Path

from simulation.replay.recorder import ReplayRecorder
from simulation.replay.results import build_battle_report_summary
from simulation.replay.storage import ReplayStorage

self._recording_enabled = False
self._active_replay_id: str | None = None
self._replay_recorder = ReplayRecorder(snapshot_interval_seconds=2.5)
self._replay_storage = ReplayStorage(
    get_project_data_dir() / "replays",
    get_project_data_dir() / "battle_reports",
)
self._battle_reports_cache = self._replay_storage.list_reports()
```

- [ ] **Step 4: 在工具栏增加 `录制 / 结算 / 战绩`**

在 `_build_toolbar()` 中新增三个 `QAction`：

```python
self.record_action = QAction("录制", self)
self.record_action.setCheckable(True)
self.record_action.triggered.connect(self._handle_record_toggled)

self.settle_action = QAction("结算", self)
self.settle_action.triggered.connect(self._settle_recorded_run)

self.reports_action = QAction("战绩", self)
self.reports_action.triggered.connect(self._show_battle_report_dialog)

toolbar.addAction(self.record_action)
toolbar.addAction(self.settle_action)
toolbar.addAction(self.reports_action)
```

- [ ] **Step 5: 实现录制开关与会话开始**

```python
def _handle_record_toggled(self, checked: bool) -> None:
    self._set_recording_enabled(bool(checked))

def _set_recording_enabled(self, enabled: bool) -> None:
    self._recording_enabled = enabled
    if not enabled:
        self.statusBar().showMessage("已关闭录制", 1500)
        return
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    self._active_replay_id = f"{timestamp}-{self.scenario.name}"
    self._replay_recorder.start(
        replay_id=self._active_replay_id,
        scenario_name=self.scenario.name,
        started_at=datetime.now().isoformat(timespec="seconds"),
        initial_state=self.map_canvas.export_replay_state(),
    )
    self.statusBar().showMessage("已开启录制", 1500)
```

- [ ] **Step 6: 在 MapCanvas 暴露回放状态导出**

在 `D:\project-simulation\simulation\ui\map_canvas.py` 增加：

```python
def export_replay_state(self) -> dict:
    return {
        "units": [
            {
                "unit_id": unit.unit_id,
                "name": unit.name,
                "side": unit.side,
                "unit_type": unit.unit_type,
                "class_name": getattr(unit, "class_name", ""),
                "alive": unit.alive,
                "position": None if unit.position is None else {"lon": unit.position.lon, "lat": unit.position.lat},
                "heading": unit.heading,
                "speed": unit.speed,
                "fuel": getattr(unit, "current_fuel", 0.0),
                "target_id": unit.target_id,
                "motion": unit.motion,
                "route_points": [{"lon": point.lon, "lat": point.lat} for point in unit.route.points],
                "weapons": [
                    {
                        "weapon_class": weapon.weapon_class,
                        "current_quantity": weapon.current_quantity,
                        "max_quantity": weapon.max_quantity,
                    }
                    for weapon in unit.weapons
                ],
            }
            for unit in self.scenario.units
        ],
        "flying_weapons": [],
        "missions": [],
        "contacts": [],
    }
```

- [ ] **Step 7: 在实时 tick 中推送周期快照与事件**

在 `MapCanvas._execute_simulation_steps()` 完成一步后追加：

```python
if hasattr(self, "replay_tick_callback") and self.replay_tick_callback is not None:
    self.replay_tick_callback(self._last_combat_step_time, self.export_replay_state())
```

并在 `MainWindow` 中绑定：

```python
self.map_canvas.replay_tick_callback = self._handle_replay_tick

def _handle_replay_tick(self, time_value: float, state: dict) -> None:
    if not self._recording_enabled or not self._replay_recorder.active:
        return
    self._replay_recorder.capture_periodic_snapshot(time_value, state)
    new_events = self.map_canvas.combat_controller.get_events_since(getattr(self, "_last_recorded_event_index", 0))
    self._last_recorded_event_index = getattr(self, "_last_recorded_event_index", 0) + len(new_events)
    for event in new_events:
        force_snapshot = event.event_type in {"detected", "launched", "hit", "unit_destroyed", "mission_completed"}
        self._replay_recorder.record_event(
            time=event.time,
            event_type=event.event_type,
            source_id=event.source_id,
            target_id=event.target_id,
            weapon_class=event.weapon_class,
            position=None if event.position is None else {"lon": event.position.lon, "lat": event.position.lat},
            message=event.message,
            force_snapshot_state=state if force_snapshot else None,
        )
```

- [ ] **Step 8: 实现手动和自动结算**

```python
def _settle_recorded_run(self) -> None:
    if not self._recording_enabled or not self._replay_recorder.active or not self._active_replay_id:
        self.statusBar().showMessage("当前未开启录制", 2000)
        return
    self._finalize_recorded_run("manual_settlement")

def _finalize_recorded_run(self, settlement_reason: str) -> None:
    finished_at = datetime.now().isoformat(timespec="seconds")
    final_state = self.map_canvas.export_replay_state()
    replay = self._replay_recorder.finish(
        ended_at=finished_at,
        duration_seconds=float(self.map_canvas.clock.current_time),
        final_state=final_state,
        settlement_reason=settlement_reason,
    )
    replay_path = self._replay_storage.save_replay(replay)
    summary = build_battle_report_summary(
        scenario=self.scenario,
        replay_id=replay.replay_id,
        finished_at=finished_at,
        duration_seconds=float(self.map_canvas.clock.current_time),
        settlement_reason=settlement_reason,
        events=replay.event_stream,
    )
    summary.replay_path = str(replay_path)
    self._replay_storage.save_report(summary)
    self._battle_reports_cache = self._replay_storage.list_reports()
    self.statusBar().showMessage("已生成战绩", 2500)
```

在 `_on_time_changed()` 或结束判定位置加：

```python
if self.map_canvas.clock.is_finished and self._recording_enabled and self._replay_recorder.active:
    self._finalize_recorded_run("simulation_finished")
```

- [ ] **Step 9: 运行 smoke 并确认通过新增断言**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\smoke_qt.py`

Expected: 新增录制/结算路径通过；如果旧 smoke 仍有无关失败，先修正为不影响本任务验证的断言

- [ ] **Step 10: 当前环境跳过 commit**

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

### Task 5: 实现战绩对话框与完整赛后页

**Files:**
- Create: `D:\project-simulation\simulation\ui\battle_report_dialog.py`
- Modify: `D:\project-simulation\simulation\ui\main_window.py`

- [ ] **Step 1: 先写一个对话框 smoke 目标**

在 `smoke_qt.py` 中增加：

```python
def _check_battle_report_dialog(window: MainWindow) -> None:
    dialog = window._build_battle_report_dialog()
    assert dialog.windowTitle() == "战绩"
```

- [ ] **Step 2: 运行 smoke，确认对话框构建能力当前缺失**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\smoke_qt.py`

Expected: FAIL，提示缺少 `_build_battle_report_dialog`

- [ ] **Step 3: 先实现最小可展示对话框**

`D:\project-simulation\simulation\ui\battle_report_dialog.py`

```python
from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


class BattleReportDialog(QDialog):
    def __init__(self, reports: list, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("战绩")
        self.resize(1280, 760)
        self._reports = reports
        self.report_list = QListWidget(self)
        self.summary_label = QLabel("请选择一条战绩", self)
        self.unit_table = QTableWidget(self)
        self.view_replay_button = QPushButton("查看回放", self)
        self.jump_button = QPushButton("跳转关键事件", self)
        self.clear_report_button = QPushButton("清除战绩记录", self)
        self.delete_all_button = QPushButton("彻底删除战绩+回放", self)
        self._build_ui()
        self._load_reports()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.addWidget(self.report_list, 1)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.summary_label)
        right_layout.addWidget(self.unit_table, 1)
        right_layout.addWidget(self.view_replay_button)
        right_layout.addWidget(self.jump_button)
        right_layout.addWidget(self.clear_report_button)
        right_layout.addWidget(self.delete_all_button)
        layout.addWidget(right, 2)

    def _load_reports(self) -> None:
        self.report_list.clear()
        for report in self._reports:
            self.report_list.addItem(
                f"{report.finished_at} | {report.scenario_name} | {report.result_label} | "
                f"蓝{report.side_summary['blue'].alive_count} 红{report.side_summary['red'].alive_count}"
            )
```

- [ ] **Step 4: 在 MainWindow 中接入对话框**

```python
from simulation.ui.battle_report_dialog import BattleReportDialog

def _build_battle_report_dialog(self) -> BattleReportDialog:
    return BattleReportDialog(self._battle_reports_cache, self)

def _show_battle_report_dialog(self) -> None:
    dialog = self._build_battle_report_dialog()
    dialog.exec_()
```

- [ ] **Step 5: 补右侧赛后页刷新逻辑**

在 `BattleReportDialog` 中继续补：

```python
self.report_list.currentRowChanged.connect(self._show_report)

def _show_report(self, row: int) -> None:
    if row < 0 or row >= len(self._reports):
        return
    report = self._reports[row]
    self.summary_label.setText(
        f"场景: {report.scenario_name}\n"
        f"结果: {report.result_label}\n"
        f"时长: {report.duration_seconds:.0f} 秒\n"
        f"蓝方存活: {report.side_summary['blue'].alive_count} / 损失: {report.side_summary['blue'].lost_count}\n"
        f"红方存活: {report.side_summary['red'].alive_count} / 损失: {report.side_summary['red'].lost_count}"
    )
    self.unit_table.setColumnCount(7)
    self.unit_table.setHorizontalHeaderLabels(["阵营", "单位", "型号", "存活", "击毁", "发射", "命中"])
    self.unit_table.setRowCount(len(report.unit_rows))
    for index, item in enumerate(report.unit_rows):
        values = [item.side, item.name, item.class_name, "是" if item.alive else "否", str(item.kills), str(item.launches), str(item.hits)]
        for column, value in enumerate(values):
            self.unit_table.setItem(index, column, QTableWidgetItem(value))
```

- [ ] **Step 6: 运行 smoke，确认对话框可打开**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\smoke_qt.py`

Expected: 战绩对话框标题和最小加载路径通过

- [ ] **Step 7: 当前环境跳过 commit**

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

### Task 6: 实现回放运行时与独立回放界面

**Files:**
- Create: `D:\project-simulation\simulation\replay\runtime.py`
- Create: `D:\project-simulation\simulation\ui\replay_viewer_dialog.py`
- Modify: `D:\project-simulation\simulation\ui\battle_report_dialog.py`
- Modify: `D:\project-simulation\simulation\ui\main_window.py`

- [ ] **Step 1: 先写运行时失败测试**

```python
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
            ReplaySnapshot(time=0.0, clock_state={"current_time": 0.0}, unit_states=[{"unit_id": "blue-1", "alive": True}], flying_weapon_states=[], mission_states=[], contact_track_states=[]),
            ReplaySnapshot(time=2.5, clock_state={"current_time": 2.5}, unit_states=[{"unit_id": "blue-1", "alive": True}], flying_weapon_states=[], mission_states=[], contact_track_states=[]),
        ],
        event_stream=[ReplayEvent(time=3.0, event_type="unit_destroyed", source_id="red-1", target_id="blue-1", weapon_class="", position=None, message="destroy", extra={})],
        highlights=[],
        final_state={"alive": {"blue": 0, "red": 1}},
    )
    runtime = ReplayRuntime(replay)
    state = runtime.seek(3.0)
    assert state["current_time"] == 3.0
    assert state["units"][0]["alive"] is False
```

- [ ] **Step 2: 运行测试并确认先失败**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_runtime.py -q`

Expected: FAIL，报找不到 `ReplayRuntime`

- [ ] **Step 3: 写最小回放运行时**

`D:\project-simulation\simulation\replay\runtime.py`

```python
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
        }
        for event in self.replay.event_stream:
            if snapshot.time < event.time <= target_time and event.event_type == "unit_destroyed":
                for unit in state["units"]:
                    if unit["unit_id"] == event.target_id:
                        unit["alive"] = False
        return state
```

- [ ] **Step 4: 写最小回放查看器**

`D:\project-simulation\simulation\ui\replay_viewer_dialog.py`

```python
from __future__ import annotations

from PyQt5.QtWidgets import QComboBox, QDialog, QListWidget, QPushButton, QVBoxLayout

from simulation.replay.runtime import ReplayRuntime


class ReplayViewerDialog(QDialog):
    def __init__(self, replay, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("回放查看")
        self.resize(1100, 720)
        self.runtime = ReplayRuntime(replay)
        self.play_button = QPushButton("播放", self)
        self.pause_button = QPushButton("暂停", self)
        self.speed_combo = QComboBox(self)
        self.speed_combo.addItems(["1x", "2x", "4x"])
        self.key_event_list = QListWidget(self)
        self._build_ui(replay)

    def _build_ui(self, replay) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self.play_button)
        layout.addWidget(self.pause_button)
        layout.addWidget(self.speed_combo)
        layout.addWidget(self.key_event_list, 1)
        for event in replay.event_stream:
            self.key_event_list.addItem(f"{event.time:06.1f}s | {event.event_type} | {event.message}")
```

- [ ] **Step 5: 从战绩页接入 `查看回放`**

在 `BattleReportDialog` 中加入回调注入：

```python
class BattleReportDialog(QDialog):
    def __init__(self, reports: list, open_replay_callback, parent=None) -> None:
        ...
        self._open_replay_callback = open_replay_callback
        self.view_replay_button.clicked.connect(self._open_selected_replay)

    def _open_selected_replay(self) -> None:
        row = self.report_list.currentRow()
        if row < 0 or row >= len(self._reports):
            return
        self._open_replay_callback(self._reports[row])
```

在 `MainWindow` 中加入：

```python
from simulation.ui.replay_viewer_dialog import ReplayViewerDialog

def _open_replay_from_report(self, report) -> None:
    if not report.has_replay:
        self.statusBar().showMessage("该战绩没有可用回放", 2000)
        return
    replay = self._replay_storage.load_replay(report.replay_id)
    dialog = ReplayViewerDialog(replay, self)
    dialog.exec_()
```

- [ ] **Step 6: 运行新增 runtime 测试**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_runtime.py -q`

Expected: PASS，输出 `1 passed`

- [ ] **Step 7: 运行 smoke 确认回放查看器最小入口可用**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\smoke_qt.py`

Expected: 至少能构建回放查看器并加载关键事件列表

- [ ] **Step 8: 当前环境跳过 commit**

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

### Task 7: 实现战绩清理与回放删除

**Files:**
- Modify: `D:\project-simulation\simulation\replay\storage.py`
- Modify: `D:\project-simulation\simulation\ui\battle_report_dialog.py`
- Modify: `D:\project-simulation\simulation\tests\test_replay_storage.py`
- Modify: `D:\project-simulation\simulation\tools\smoke_qt.py`

- [ ] **Step 1: 先写删除行为失败测试**

```python
def test_replay_storage_can_delete_report_only(tmp_path: Path) -> None:
    storage = ReplayStorage(tmp_path / "replays", tmp_path / "battle_reports")
    replay = ...
    summary = ...
    storage.save_replay(replay)
    storage.save_report(summary)

    storage.delete_report_only("report-1")

    assert (tmp_path / "battle_reports" / "report-1.json").exists() is False
    assert (tmp_path / "replays" / "replay-1.json").exists() is True


def test_replay_storage_can_delete_report_and_replay(tmp_path: Path) -> None:
    storage = ReplayStorage(tmp_path / "replays", tmp_path / "battle_reports")
    replay = ...
    summary = ...
    storage.save_replay(replay)
    storage.save_report(summary)

    storage.delete_report_and_replay("report-1", "replay-1")

    assert (tmp_path / "battle_reports" / "report-1.json").exists() is False
    assert (tmp_path / "replays" / "replay-1.json").exists() is False
```

- [ ] **Step 2: 运行测试并确认先失败**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_storage.py -q`

Expected: FAIL，提示缺少删除接口

- [ ] **Step 3: 在存储层补删除接口**

在 `storage.py` 中增加：

```python
def delete_report_only(self, report_id: str) -> None:
    path = self.report_dir / f"{report_id}.json"
    if path.exists():
        path.unlink()

def delete_report_and_replay(self, report_id: str, replay_id: str) -> None:
    self.delete_report_only(report_id)
    replay_path = self.replay_dir / f"{replay_id}.json"
    if replay_path.exists():
        replay_path.unlink()
```

- [ ] **Step 4: 在战绩对话框接入删除动作**

在 `BattleReportDialog` 中新增回调：

```python
class BattleReportDialog(QDialog):
    def __init__(self, reports: list, open_replay_callback, delete_report_callback, delete_all_callback, parent=None) -> None:
        ...
        self._delete_report_callback = delete_report_callback
        self._delete_all_callback = delete_all_callback
        self.clear_report_button.clicked.connect(self._delete_report_only)
        self.delete_all_button.clicked.connect(self._delete_report_and_replay)

    def _delete_report_only(self) -> None:
        row = self.report_list.currentRow()
        if row < 0:
            return
        self._delete_report_callback(self._reports[row], False)

    def _delete_report_and_replay(self) -> None:
        row = self.report_list.currentRow()
        if row < 0:
            return
        self._delete_report_callback(self._reports[row], True)
```

在 `MainWindow` 中实现：

```python
def _delete_battle_report(self, report, delete_replay: bool) -> None:
    if delete_replay:
        self._replay_storage.delete_report_and_replay(report.report_id, report.replay_id)
    else:
        self._replay_storage.delete_report_only(report.report_id)
    self._battle_reports_cache = self._replay_storage.list_reports()
```

- [ ] **Step 5: 运行删除测试确认通过**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests\test_replay_storage.py -q`

Expected: PASS，输出 `3 passed` 或更多

- [ ] **Step 6: 更新 smoke，验证至少一条删除路径**

在 `smoke_qt.py` 中加入：

```python
def _check_report_delete_flow(window: MainWindow) -> None:
    if not window._battle_reports_cache:
        return
    report = window._battle_reports_cache[0]
    replay_path = Path(report.replay_path)
    window._delete_battle_report(report, False)
    assert replay_path.exists() or not replay_path.is_absolute()
```

- [ ] **Step 7: 运行 smoke**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\smoke_qt.py`

Expected: 战绩删除路径基础通过

- [ ] **Step 8: 当前环境跳过 commit**

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

### Task 8: 收口验证、补文档、整理回归检查

**Files:**
- Modify: `D:\project-simulation\simulation\tools\smoke_qt.py`
- Modify: `D:\project-simulation\simulation\docs\manual_qa_checklist.md`
- Modify: `D:\project-simulation\simulation\docs\project_optimization_plan.md`

- [ ] **Step 1: 给 manual QA 增加回放与战绩条目**

在 `manual_qa_checklist.md` 中加入：

```md
## Replay And Battle Reports
- [ ] Turn recording on, run a short simulation, and confirm a battle report is created.
- [ ] Trigger manual settlement and confirm a partial battle report is created.
- [ ] Open `战绩` and confirm the list loads.
- [ ] Select one report and verify side summary and unit table content.
- [ ] Open replay and jump to at least one key event.
- [ ] Clear report only and confirm the replay file remains.
- [ ] Delete report and replay together and confirm both disappear.
```

- [ ] **Step 2: 在项目优化计划里登记这一轮完成项**

在 `project_optimization_plan.md` 的当前完成段落追加：

```md
- Added replay recording toggle, manual settlement, battle report storage, and a dedicated battle-report dialog.
- Added a lightweight replay viewer driven by replay snapshots and event stream rather than the live simulation runtime.
- Added two cleanup levels for reports and replay files.
```

- [ ] **Step 3: 运行单元测试全集**

Run: `D:\software\Anaconda\envs\python3.11\python.exe -m pytest simulation\tests -q`

Expected: PASS，新增 replay 相关测试全部通过

- [ ] **Step 4: 运行项目校验脚本**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\validate_project.py`

Expected: `Project validation passed.`

- [ ] **Step 5: 运行 Qt smoke**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\tools\smoke_qt.py`

Expected: `Qt smoke checks passed.`，或修复现有无关失败直到输出干净通过

- [ ] **Step 6: 做一次手工冒烟**

Run: `D:\software\Anaconda\envs\python3.11\python.exe simulation\main.py`

Expected:
- 工具栏能看到 `录制 / 结算 / 战绩`
- 开启录制后运行一局能生成战绩
- `战绩` 对话框能打开
- 能打开回放
- 能执行两级删除

- [ ] **Step 7: 当前环境跳过 commit**

Run: `git status --short`

Expected: FAIL with `fatal: not a git repository`

## 计划自检

### 覆盖检查

本计划覆盖了 spec 中的关键要求：

- 工具栏新增 `录制 / 结算 / 战绩`
- `2.5 秒` 快照与关键事件补快照
- 自动和手动结算
- 战绩摘要与完整赛后页
- 独立回放界面
- 只删战绩 / 删战绩+回放
- smoke、单测、人工 QA

### 占位词检查

本计划未使用 `TODO`、`TBD`、`implement later` 之类占位描述。所有任务都给了明确文件路径、命令和最小代码方向。

### 命名一致性检查

本计划统一使用：

- `ReplayStorage`
- `ReplayRecorder`
- `ReplayRuntime`
- `BattleReportDialog`
- `ReplayViewerDialog`
- `build_battle_report_summary`

避免后续实现过程中出现同一能力多套命名。
