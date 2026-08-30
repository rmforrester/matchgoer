from config.leagues import EUROPE_APPROVED_2026, EUROPE_GAP_CLEARED_2026, ENGLAND_PYRAMID_2026, USA_PRIORITY_2026, SWEDEN_PRIORITY_2026, LeagueScope
from ingest_leagues import resolve_scope


EXPECTED_ENGLAND_LEAGUE_IDS = {
    "Premier League": 39,
    "Championship": 40,
    "League One": 41,
    "League Two": 42,
    "National League": 43,
    "National League - North": 50,
    "National League - South": 51,
    "Non League Premier - Isthmian": 58,
    "Non League Premier - Northern": 59,
    "Non League Premier - Southern Central": 931,
    "Non League Premier - Southern South": 60,
    "Non League Div One - Isthmian North": 52,
    "Non League Div One - Isthmian South Central": 53,
    "Non League Div One - Isthmian South East": 57,
    "Non League Div One - Northern East": 932,
    "Non League Div One - Northern Midlands": 55,
    "Non League Div One - Northern West": 54,
    "Non League Div One - Southern Central": 933,
    "Non League Div One - Southern South": 56,
}


def test_england_pyramid_has_canonical_api_football_ids():
    actual = {scope.display_name: scope.league_id for scope in ENGLAND_PYRAMID_2026}

    assert actual == EXPECTED_ENGLAND_LEAGUE_IDS
    assert len(set(actual.values())) == 19


def test_other_country_profiles_are_unchanged():
    assert [scope.league_id for scope in USA_PRIORITY_2026] == [None, None, None]
    assert [scope.league_id for scope in SWEDEN_PRIORITY_2026] == [
        113, 114, 563, 564, 592, 593, 594, 595, 596, 597
    ]


def test_explicit_league_id_bypasses_runtime_resolution():
    configured = ENGLAND_PYRAMID_2026[0]

    class UnexpectedLookupClient:
        def leagues_by_country(self, country):
            raise AssertionError(f"unexpected runtime lookup for {country}")

    assert resolve_scope(UnexpectedLookupClient(), configured) is configured


def test_europe_approved_profile_is_exact_and_explicit():
    assert len(EUROPE_APPROVED_2026) == 20
    assert [scope.league_id for scope in EUROPE_APPROVED_2026] == [
        218, 219, 119, 120, 122, 62, 78, 79, 85, 758,
        135, 136, 88, 89, 103, 180, 183, 730, 436, 207,
    ]
    assert all(scope.league_id is not None for scope in EUROPE_APPROVED_2026)


def test_europe_gap_cleared_profile_is_exact_and_explicit():
    assert [(scope.country, scope.league_id) for scope in EUROPE_GAP_CLEARED_2026] == [
        ("Spain", 140),
        ("France", 61),
        ("Czech-Republic", 345),
        ("Poland", 106),
        ("Turkey", 203),
        ("Scotland", 179),
    ]
    assert all(scope.provider_season == 2026 for scope in EUROPE_GAP_CLEARED_2026)


def test_unmapped_scope_uses_runtime_name_resolution():
    configured = LeagueScope("USA", None, "Major League Soccer", 2026, "2026", ("MLS",))

    class DiscoveryClient:
        def __init__(self):
            self.countries = []

        def leagues_by_country(self, country):
            self.countries.append(country)
            return [{"league": {"id": 253, "name": "Major League Soccer"}}]

    client = DiscoveryClient()
    resolved = resolve_scope(client, configured)

    assert client.countries == ["USA"]
    assert resolved.league_id == 253
    assert resolved.display_name == configured.display_name
    assert resolved.provider_season == configured.provider_season
    assert resolved.display_season == configured.display_season
    assert resolved.aliases == configured.aliases
