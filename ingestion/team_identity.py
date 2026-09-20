"""Provider-independent team allocation and scoped identity resolution primitives.

Job A deliberately does not wire these primitives into fixture ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

from sqlalchemy import text


class TeamIdentityError(ValueError):
    pass


class IdentityResolution(str, Enum):
    IDENTITY_COMPATIBLE = "IDENTITY_COMPATIBLE"
    REVIEWED_SCOPED_OVERRIDE = "REVIEWED_SCOPED_OVERRIDE"
    NEW_PROVIDER_TEAM = "NEW_PROVIDER_TEAM"
    NEEDS_IDENTITY_REVIEW = "NEEDS_IDENTITY_REVIEW"


@dataclass(frozen=True)
class CanonicalTeam:
    canonical_team_id: int
    canonical_name: str


@dataclass(frozen=True)
class TeamIdentityOverride:
    provider: str
    provider_team_id: int
    league_id: int
    season: int
    canonical_team_id: int
    expected_provider_name: str
    review_status: str


@dataclass(frozen=True)
class TeamIdentityResult:
    outcome: IdentityResolution
    canonical_team_id: int | None
    reason: str


def validate_provider_team_id(provider_team_id: int) -> int:
    if isinstance(provider_team_id, bool) or not isinstance(provider_team_id, int):
        raise TeamIdentityError("provider team ID must be an integer")
    if provider_team_id <= 0:
        raise TeamIdentityError("provider team ID must be positive")
    return provider_team_id


def validate_internal_team_id(canonical_team_id: int) -> int:
    if isinstance(canonical_team_id, bool) or not isinstance(canonical_team_id, int):
        raise TeamIdentityError("internal team ID must be an integer")
    if canonical_team_id >= 0:
        raise TeamIdentityError("internal team ID must be negative")
    return canonical_team_id


def normalize_team_name(value: str) -> str:
    """Normalize only case, accents, whitespace and punctuation."""
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def team_names_compatible(observed_name: str, expected_name: str) -> bool:
    observed = normalize_team_name(observed_name)
    expected = normalize_team_name(expected_name)
    return bool(observed and expected and observed == expected)


def allocate_internal_team_id(connection) -> int:
    """Allocate from PostgreSQL's transaction-safe, negative-only sequence."""
    allocated = connection.execute(
        text("SELECT nextval('matchgoer_team_id_seq')")
    ).scalar_one()
    return validate_internal_team_id(int(allocated))


def resolve_team_identity(
    *,
    provider: str,
    provider_team_id: int,
    observed_name: str,
    league_id: int,
    season: int,
    canonical_team: CanonicalTeam | None,
    overrides: tuple[TeamIdentityOverride, ...] | list[TeamIdentityOverride] = (),
) -> TeamIdentityResult:
    validate_provider_team_id(provider_team_id)
    if not str(provider or "").strip():
        raise TeamIdentityError("provider must be nonblank")
    if not isinstance(league_id, int) or isinstance(league_id, bool) or league_id <= 0:
        raise TeamIdentityError("league ID must be positive")
    if not isinstance(season, int) or isinstance(season, bool) or season <= 0:
        raise TeamIdentityError("season must be positive")

    exact = [
        override for override in overrides
        if override.review_status == "APPROVED"
        and override.provider == provider
        and override.provider_team_id == provider_team_id
        and override.league_id == league_id
        and override.season == season
    ]
    if len(exact) > 1:
        raise TeamIdentityError("multiple approved overrides for one identity scope")
    if exact:
        override = exact[0]
        if not team_names_compatible(observed_name, override.expected_provider_name):
            return TeamIdentityResult(
                IdentityResolution.NEEDS_IDENTITY_REVIEW,
                None,
                "observed name conflicts with reviewed scoped override",
            )
        if override.canonical_team_id == 0:
            raise TeamIdentityError("override canonical team ID must be nonzero")
        return TeamIdentityResult(
            IdentityResolution.REVIEWED_SCOPED_OVERRIDE,
            override.canonical_team_id,
            "exact approved provider/league/season override",
        )

    if canonical_team is None:
        return TeamIdentityResult(
            IdentityResolution.NEW_PROVIDER_TEAM,
            provider_team_id,
            "unseen positive provider team ID",
        )
    if canonical_team.canonical_team_id != provider_team_id:
        raise TeamIdentityError("ordinary canonical lookup must use the provider team ID")
    if team_names_compatible(observed_name, canonical_team.canonical_name):
        return TeamIdentityResult(
            IdentityResolution.IDENTITY_COMPATIBLE,
            canonical_team.canonical_team_id,
            "observed and established canonical names are compatible",
        )
    return TeamIdentityResult(
        IdentityResolution.NEEDS_IDENTITY_REVIEW,
        None,
        "established provider-derived canonical has a materially different name",
    )
