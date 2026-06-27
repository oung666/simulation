from __future__ import annotations

from dataclasses import dataclass

from simulation.core.geo import LonLat


CONTACT_STALE_AFTER_S = 30.0
CONTACT_EXPIRE_AFTER_S = 90.0


@dataclass
class ContactTrack:
    target_id: str
    side: str
    last_known_position: LonLat
    last_detected_time: float
    source_unit_id: str
    confidence: float = 1.0
    track_type: str = "local"
    shared: bool = False

    def age_s(self, current_time: float) -> float:
        return max(0.0, current_time - self.last_detected_time)

    def is_stale(self, current_time: float) -> bool:
        return self.age_s(current_time) > CONTACT_STALE_AFTER_S

    def is_expired(self, current_time: float) -> bool:
        return self.age_s(current_time) > CONTACT_EXPIRE_AFTER_S

    def decayed_confidence(self, current_time: float) -> float:
        freshness = max(0.0, 1.0 - self.age_s(current_time) / CONTACT_EXPIRE_AFTER_S)
        return max(0.0, min(1.0, self.confidence * freshness))
