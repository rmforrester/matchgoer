"""Small, fail-safe fixture taxonomy for Discover presentation."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal


FixtureType = Literal["standard", "cup", "international"]


def _normalise(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).split())


def classify_fixture_type(league_name: str | None, country: str | None = None) -> FixtureType:
    """Derive the three-state Discover marker type from existing competition metadata.

    Unknown or incomplete metadata deliberately falls back to ``standard``.
    International signals are evaluated before the general cup vocabulary so names
    such as World Cup and Africa Cup of Nations remain national-team fixtures.
    """

    name = _normalise(league_name)
    competition_country = _normalise(country)
    if not name:
        return "standard"

    club_overrides = (
        "club world cup",
        "international champions cup",
    )
    if any(signal in name for signal in club_overrides):
        return "cup"

    international_signals = (
        "world cup",
        "nations league",
        "european championship",
        "euro championship",
        "euro qualification",
        "euro qualifiers",
        "africa cup of nations",
        "asian cup",
        "copa america",
        "gold cup",
        "confederations cup",
        "finalissima",
        "international friendly",
        "international friendlies",
    )
    if any(signal in name for signal in international_signals):
        return "international"
    if name == "friendlies" and competition_country == "world":
        return "international"
    if "qualification" in name and any(
        signal in name
        for signal in ("world", "uefa", "euro", "africa", "asia", "concacaf", "conmebol", "ofc")
    ):
        return "international"

    cup_signals = (
        "cup",
        "copa",
        "coupe",
        "coppa",
        "pokal",
        "taca",
        "trophy",
        "shield",
        "super cup",
        "supercup",
        "champions league",
        "europa league",
        "conference league",
        "libertadores",
        "sudamericana",
    )
    if any(signal in name for signal in cup_signals):
        return "cup"

    return "standard"
