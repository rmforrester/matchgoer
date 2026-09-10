"""Fail-closed validation shared by BTM publication workflows."""

from __future__ import annotations


def validate_btm_navigation(*, maps_destination: str | None, unique_target_supported: bool) -> None:
    """Reject an active Directions target without affirmative unique-identity support.

    A BTM remains publishable without Directions; callers should retain truthful
    location_context and pass ``maps_destination=None`` when precision is absent.
    """
    active = bool(maps_destination and maps_destination.strip())
    if active and not unique_target_supported:
        raise ValueError("BTM Directions requires an evidence-supported unique physical target")

