"""Provider-independent team allocation and scoped identity resolution primitives.

Job A deliberately does not wire these primitives into fixture ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

from sqlalchemy import bindparam, text

IDENTITY_RESOLVER_VERSION = "team-identity-option1-v1"
ACCEPTABLE_IDENTITY_RESOLUTIONS = {
    "IDENTITY_COMPATIBLE", "REVIEWED_SCOPED_OVERRIDE", "NEW_PROVIDER_TEAM",
}


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
    override_id: int | None = None


@dataclass(frozen=True)
class TeamIdentityResult:
    outcome: IdentityResolution
    canonical_team_id: int | None
    reason: str


@dataclass(frozen=True)
class ProviderTeamObservation:
    provider: str
    provider_team_id: int
    observed_name: str
    league_id: int
    season: int
    country: str | None = None

    @property
    def key(self) -> tuple[str, int, str, int, int]:
        return (self.provider, self.provider_team_id, self.observed_name, self.league_id, self.season)


@dataclass(frozen=True)
class IdentityResolutionReceipt:
    provider: str
    provider_team_id: int
    canonical_team_id: int | None
    observed_name: str
    canonical_name: str | None
    league_id: int
    season: int
    identity_resolution: str
    approved_override_id: int | None
    resolver_version: str = IDENTITY_RESOLVER_VERSION

    def serializable(self) -> dict:
        return {
            "provider": self.provider,
            "provider_team_id": self.provider_team_id,
            "canonical_team_id": self.canonical_team_id,
            "observed_name": self.observed_name,
            "canonical_name": self.canonical_name,
            "league_id": self.league_id,
            "season": self.season,
            "identity_resolution": self.identity_resolution,
            "approved_override_id": self.approved_override_id,
            "resolver_version": self.resolver_version,
        }


class TeamIdentityReviewRequired(TeamIdentityError):
    def __init__(self, receipts: list[IdentityResolutionReceipt]):
        self.receipts = receipts
        super().__init__(f"{len(receipts)} provider team observation(s) require identity review")


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


def resolve_provider_team_batch(connection, observations: list[ProviderTeamObservation]) -> dict[tuple[str, int, str, int, int], IdentityResolutionReceipt]:
    """Resolve each unique provider observation with two or three bounded reads."""
    unique = {observation.key: observation for observation in observations}
    if not unique:
        return {}
    provider_ids = sorted({observation.provider_team_id for observation in unique.values()})
    team_query = text(
        "SELECT team_id, team_name FROM teams WHERE team_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    canonical = {
        int(row["team_id"]): CanonicalTeam(int(row["team_id"]), row["team_name"] or "")
        for row in connection.execute(team_query, {"ids": provider_ids}).mappings()
    }
    override_query = text("""
        SELECT team_identity_override_id, provider, provider_team_id, league_id,
               season, canonical_team_id, expected_provider_name, review_status
        FROM team_identity_overrides
        WHERE provider_team_id IN :ids
    """).bindparams(bindparam("ids", expanding=True))
    overrides = [
        TeamIdentityOverride(
            provider=row["provider"], provider_team_id=int(row["provider_team_id"]),
            league_id=int(row["league_id"]), season=int(row["season"]),
            canonical_team_id=int(row["canonical_team_id"]),
            expected_provider_name=row["expected_provider_name"],
            review_status=row["review_status"], override_id=int(row["team_identity_override_id"]),
        )
        for row in connection.execute(override_query, {"ids": provider_ids}).mappings()
    ]
    canonical_ids = {override.canonical_team_id for override in overrides if override.review_status == "APPROVED"}
    missing_canonical_ids = sorted(canonical_ids - set(canonical))
    if missing_canonical_ids:
        extra = {
            int(row["team_id"]): CanonicalTeam(int(row["team_id"]), row["team_name"] or "")
            for row in connection.execute(team_query, {"ids": missing_canonical_ids}).mappings()
        }
        canonical.update(extra)

    receipts = {}
    for key, observation in unique.items():
        matching_overrides = [
            override for override in overrides
            if override.provider == observation.provider
            and override.provider_team_id == observation.provider_team_id
            and override.league_id == observation.league_id
            and override.season == observation.season
        ]
        result = resolve_team_identity(
            provider=observation.provider,
            provider_team_id=observation.provider_team_id,
            observed_name=observation.observed_name,
            league_id=observation.league_id,
            season=observation.season,
            canonical_team=canonical.get(observation.provider_team_id),
            overrides=matching_overrides,
        )
        approved = next((item for item in matching_overrides if item.review_status == "APPROVED"), None)
        resolved_team = canonical.get(result.canonical_team_id) if result.canonical_team_id is not None else None
        if result.outcome == IdentityResolution.REVIEWED_SCOPED_OVERRIDE and resolved_team is None:
            result = TeamIdentityResult(
                IdentityResolution.NEEDS_IDENTITY_REVIEW,
                None,
                "reviewed scoped override canonical team is missing",
            )
        canonical_name = resolved_team.canonical_name if resolved_team else (
            observation.observed_name if result.outcome == IdentityResolution.NEW_PROVIDER_TEAM else None
        )
        receipts[key] = IdentityResolutionReceipt(
            provider=observation.provider,
            provider_team_id=observation.provider_team_id,
            canonical_team_id=result.canonical_team_id,
            observed_name=observation.observed_name,
            canonical_name=canonical_name,
            league_id=observation.league_id,
            season=observation.season,
            identity_resolution=result.outcome.value,
            approved_override_id=approved.override_id if result.outcome == IdentityResolution.REVIEWED_SCOPED_OVERRIDE and approved else None,
        )
    return receipts
