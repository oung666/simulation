from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt5.QtWidgets import QWidget


@dataclass
class OverlayRegistration:
    name: str
    widget: QWidget
    reposition: Callable[[], None] | None = None


class OverlayManager:
    """Small coordinator for map-hosted floating widgets."""

    def __init__(self) -> None:
        self._registrations: dict[str, OverlayRegistration] = {}

    def register(self, name: str, widget: QWidget, reposition: Callable[[], None] | None = None) -> None:
        self._registrations[name] = OverlayRegistration(name, widget, reposition)

    def raise_overlay(self, name: str) -> None:
        registration = self._registrations.get(name)
        if registration is not None:
            registration.widget.raise_()

    def reposition(self, name: str) -> None:
        registration = self._registrations.get(name)
        if registration is not None and registration.reposition is not None:
            registration.reposition()

    def reposition_all(self) -> None:
        for registration in self._registrations.values():
            if registration.reposition is not None:
                registration.reposition()

    def hide(self, name: str) -> None:
        registration = self._registrations.get(name)
        if registration is not None:
            registration.widget.hide()
