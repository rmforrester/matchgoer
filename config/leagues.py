"""Declarative league scopes used by the Matchgoer ingestion tools."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueScope:
    country: str
    league_id: int | None
    display_name: str
    provider_season: int
    display_season: str
    aliases: tuple[str, ...] = ()


ENGLAND_PYRAMID_2026 = (
    LeagueScope("England", 39, "Premier League", 2026, "2026/27"),
    LeagueScope("England", 40, "Championship", 2026, "2026/27"),
    LeagueScope("England", 41, "League One", 2026, "2026/27"),
    LeagueScope("England", 42, "League Two", 2026, "2026/27"),
    LeagueScope("England", 43, "National League", 2026, "2026/27"),
    LeagueScope("England", 50, "National League - North", 2026, "2026/27", ("National League North",)),
    LeagueScope("England", 51, "National League - South", 2026, "2026/27", ("National League South",)),
    LeagueScope("England", 58, "Non League Premier - Isthmian", 2026, "2026/27"),
    LeagueScope("England", 59, "Non League Premier - Northern", 2026, "2026/27"),
    LeagueScope("England", 931, "Non League Premier - Southern Central", 2026, "2026/27"),
    LeagueScope("England", 60, "Non League Premier - Southern South", 2026, "2026/27"),
    LeagueScope("England", 52, "Non League Div One - Isthmian North", 2026, "2026/27"),
    LeagueScope("England", 53, "Non League Div One - Isthmian South Central", 2026, "2026/27"),
    LeagueScope("England", 57, "Non League Div One - Isthmian South East", 2026, "2026/27"),
    LeagueScope("England", 932, "Non League Div One - Northern East", 2026, "2026/27"),
    LeagueScope("England", 55, "Non League Div One - Northern Midlands", 2026, "2026/27"),
    LeagueScope("England", 54, "Non League Div One - Northern West", 2026, "2026/27"),
    LeagueScope("England", 933, "Non League Div One - Southern Central", 2026, "2026/27"),
    LeagueScope("England", 56, "Non League Div One - Southern South", 2026, "2026/27"),
)

USA_PRIORITY_2026 = (
    LeagueScope("USA", None, "Major League Soccer", 2026, "2026", ("MLS",)),
    LeagueScope("USA", None, "USL Championship", 2026, "2026"),
    LeagueScope("USA", None, "USL League One", 2026, "2026"),
)

SWEDEN_PRIORITY_2026 = (
    LeagueScope("Sweden", 113, "Allsvenskan", 2026, "2026"),
    LeagueScope("Sweden", 114, "Superettan", 2026, "2026"),
    LeagueScope("Sweden", 563, "Ettan - Norra", 2026, "2026"),
    LeagueScope("Sweden", 564, "Ettan - Södra", 2026, "2026"),
    LeagueScope("Sweden", 592, "Division 2 - Norra Götaland", 2026, "2026"),
    LeagueScope("Sweden", 593, "Division 2 - Norra Svealand", 2026, "2026"),
    LeagueScope("Sweden", 594, "Division 2 - Norrland", 2026, "2026"),
    LeagueScope("Sweden", 595, "Division 2 - Södra Svealand", 2026, "2026"),
    LeagueScope("Sweden", 596, "Division 2 - Västra Götaland", 2026, "2026"),
    LeagueScope("Sweden", 597, "Division 2 - Södra Götaland", 2026, "2026"),
)

COVERAGE_PROFILES = {
    "england-pyramid": ENGLAND_PYRAMID_2026,
    "usa-priority": USA_PRIORITY_2026,
    "sweden-priority": SWEDEN_PRIORITY_2026,
}
