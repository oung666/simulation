from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class SimulationClock:
    """Independent simulation clock, decoupled from UI frame rate.

    Mirrors Panopticon''s design:
    - current_time is the authoritative logical time (seconds, integer steps).
    - time_compression controls how many logical steps per UI tick.
    - The clock owns play/pause/reset; the UI layer no longer manages time directly.
    """

    start_time: float = 0.0
    duration: float = 3600.0
    time_compression: int = 1
    step_size: float = 1.0  # seconds per logical step, always 1.0 for Panopticon-style
    paused: bool = True
    current_time: float = 0.0
    elapsed_real_ms: float = 0.0
    _last_wall_time: float = field(default_factory=time.monotonic)
    _sim_carry_s: float = 0.0

    # --- lifecycle ---

    def reset(self) -> None:
        """Reset clock to scenario start."""
        self.current_time = self.start_time
        self.paused = True
        self.elapsed_real_ms = 0.0
        self._sim_carry_s = 0.0
        self._last_wall_time = time.monotonic()

    # --- playback control ---

    def play(self) -> None:
        self.paused = False
        self._last_wall_time = time.monotonic()

    def pause(self) -> None:
        self.paused = True

    def toggle(self) -> None:
        if self.paused:
            self.play()
        else:
            self.pause()

    # --- speed ---

    def set_time_compression(self, value: int) -> None:
        self.time_compression = max(1, value)

    def step_once(self, steps: int = 1) -> int:
        """Advance the simulation by an exact number of logical steps."""
        actual_steps = max(0, int(steps))
        if actual_steps <= 0:
            return 0
        self.current_time += actual_steps * self.step_size
        if self.is_finished:
            self.current_time = self.start_time + self.duration
            self.paused = True
        return actual_steps

    def cycle_compression(self, compressions: list[int] | None = None) -> int:
        """Cycle to the next compression level (Panopticon-style)."""
        levels = compressions or [1, 2, 4, 8, 100]
        try:
            idx = levels.index(self.time_compression)
            self.time_compression = levels[(idx + 1) % len(levels)]
        except ValueError:
            self.time_compression = levels[0]
        return self.time_compression

    # --- tick ---

    def tick(self) -> int:
        """Advance the clock for one UI tick.

        Accumulates real wall-clock time and converts it to simulation
        steps using time_compression.  At 1x compression, 1 real second
        advances the simulation by 1 second.  At 100x, 1 real second
        advances 100 simulation seconds.

        Returns the number of 1-second logical steps to execute this tick.
        """
        if self.paused:
            return 0

        now = time.monotonic()
        real_delta_s = now - self._last_wall_time
        self._last_wall_time = now
        self.elapsed_real_ms += real_delta_s * 1000.0

        self._sim_carry_s += real_delta_s * self.time_compression
        steps = int(self._sim_carry_s / self.step_size)
        if steps <= 0:
            return 0

        self._sim_carry_s -= steps * self.step_size
        self.current_time += steps * self.step_size
        if self.is_finished:
            self.current_time = self.start_time + self.duration
            self.paused = True
            self._sim_carry_s = 0.0
        return steps

    # --- queries ---

    def progress(self) -> float:
        """Return 0.0–1.0 for progress bars."""
        if self.duration <= 0:
            return 0.0
        return min(1.0, (self.current_time - self.start_time) / self.duration)

    @property
    def is_finished(self) -> bool:
        return self.current_time >= self.start_time + self.duration

    @property
    def is_playing(self) -> bool:
        return not self.paused

    def format_time(self) -> str:
        """Return HH:MM:SS string for status bar."""
        total = int(self.current_time)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def fractional_time(self) -> float:
        """Return current time including the not-yet-materialized partial step."""
        return self.current_time + min(self._sim_carry_s, self.step_size)
