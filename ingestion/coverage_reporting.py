"""Small, read-only coverage lifecycle helpers for provider league audits."""

from __future__ import annotations

from dataclasses import dataclass


REMEDIATION_REQUIRED = "REMEDIATION_REQUIRED"
SAFE_TO_IMPORT = "SAFE_TO_IMPORT"
WITHHOLD_WITH_REASON = "WITHHOLD_WITH_REASON"
SAFE_UNDER_REVISED_POLICY = "SAFE_UNDER_REVISED_POLICY"
PARTIAL_FIXTURE_REMEDIATION_REQUIRED = "PARTIAL_FIXTURE_REMEDIATION_REQUIRED"
LEAGUE_LEVEL_BLOCKER = "LEAGUE_LEVEL_BLOCKER"

# Breadth imports must retain only reviewed/checkpoint coordinates. The
# importer already represents every other coordinate as NULL.
BREADTH_IMPORT_GEOCODE = False


@dataclass(frozen=True)
class CoverageLeague:
    country: str
    league_id: int
    name: str
    level: int
    provider_available: bool
    hosted_complete: bool = False
    safety_passed: bool = False
    blocker_reasons: tuple[str, ...] = ()
    excluded_reason: str | None = None


def lifecycle_status(league: CoverageLeague) -> str:
    """Keep every discovered league visible after preflight."""
    if league.excluded_reason or not league.provider_available:
        return WITHHOLD_WITH_REASON
    if league.hosted_complete or league.safety_passed:
        return SAFE_TO_IMPORT
    return REMEDIATION_REQUIRED


def revised_breadth_status(
    *,
    provider_available: bool,
    identity_collisions: int = 0,
    material_venue_contradictions: int = 0,
    unresolved_fixture_links: int = 0,
) -> str:
    """Classify a provider-backed breadth scope without making coordinates a gate.

    Missing coordinates are intentionally absent from this contract: they are a
    feature-readiness metric, while location endpoints already fail closed for
    NULL venue coordinates. A missing fixture-to-venue link is isolated at
    fixture level because ``fixtures.venue_id`` is nullable.
    """
    if not provider_available or identity_collisions or material_venue_contradictions:
        return LEAGUE_LEVEL_BLOCKER
    if unresolved_fixture_links:
        return PARTIAL_FIXTURE_REMEDIATION_REQUIRED
    return SAFE_UNDER_REVISED_POLICY


def coverage_warnings(leagues: list[CoverageLeague]) -> list[dict[str, object]]:
    """Report famous-league and discovery-depth holes without changing gates."""
    warnings: list[dict[str, object]] = []
    by_country: dict[str, list[CoverageLeague]] = {}
    for league in leagues:
        if league.provider_available and not league.excluded_reason:
            by_country.setdefault(league.country, []).append(league)

    for country, rows in sorted(by_country.items()):
        hosted_levels = {row.level for row in rows if row.hosted_complete}
        available_levels = {row.level for row in rows}
        if 1 in available_levels and 1 not in hosted_levels:
            warnings.append({"code": "TOP_FLIGHT_MISSING", "country": country, "level": 1})
        if hosted_levels and any(level > max(hosted_levels) for level in available_levels):
            warnings.append({
                "code": "DISCOVERY_DEPTH_GAP",
                "country": country,
                "deepest_hosted": max(hosted_levels),
                "deepest_available": max(available_levels),
            })
        if hosted_levels:
            deepest = max(hosted_levels)
            for level in range(1, deepest):
                if level in available_levels and level not in hosted_levels:
                    warnings.append({
                        "code": "PYRAMID_DISCONTINUITY",
                        "country": country,
                        "missing_level": level,
                        "deeper_hosted_level": min(x for x in hosted_levels if x > level),
                    })
    return warnings
