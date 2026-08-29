from config.leagues import ENGLAND_PYRAMID_2026, USA_PRIORITY_2026, SWEDEN_PRIORITY_2026


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
