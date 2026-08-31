from ingestion.coverage_reporting import (
    REMEDIATION_REQUIRED,
    SAFE_TO_IMPORT,
    WITHHOLD_WITH_REASON,
    LEAGUE_LEVEL_BLOCKER,
    PARTIAL_FIXTURE_REMEDIATION_REQUIRED,
    SAFE_UNDER_REVISED_POLICY,
    BREADTH_IMPORT_GEOCODE,
    CoverageLeague,
    coverage_warnings,
    lifecycle_status,
    revised_breadth_status,
)


def league(level, *, hosted=False, passed=False, available=True, excluded=None):
    return CoverageLeague("France", 60 + level, f"L{level}", level, available, hosted, passed, (), excluded)


def test_failed_available_league_remains_a_remediation_item():
    assert lifecycle_status(league(1)) == REMEDIATION_REQUIRED
    assert lifecycle_status(league(1, passed=True)) == SAFE_TO_IMPORT
    assert lifecycle_status(league(1, excluded="cup")) == WITHHOLD_WITH_REASON
    assert lifecycle_status(league(1, available=False)) == WITHHOLD_WITH_REASON


def test_reports_top_flight_depth_and_pyramid_gaps():
    rows = [league(1), league(2, hosted=True), league(3), league(4, hosted=True)]
    assert coverage_warnings(rows) == [
        {"code": "TOP_FLIGHT_MISSING", "country": "France", "level": 1},
        {"code": "PYRAMID_DISCONTINUITY", "country": "France", "missing_level": 1, "deeper_hosted_level": 2},
        {"code": "PYRAMID_DISCONTINUITY", "country": "France", "missing_level": 3, "deeper_hosted_level": 4},
    ]


def test_reports_discovery_depth_after_contiguous_hosted_levels():
    rows = [league(1, hosted=True), league(2, hosted=True), league(3)]
    assert coverage_warnings(rows) == [{
        "code": "DISCOVERY_DEPTH_GAP",
        "country": "France",
        "deepest_hosted": 2,
        "deepest_available": 3,
    }]


def test_revised_breadth_policy_reports_coordinates_without_using_them_as_a_gate():
    assert BREADTH_IMPORT_GEOCODE is False
    assert revised_breadth_status(provider_available=True) == SAFE_UNDER_REVISED_POLICY
    assert revised_breadth_status(provider_available=True, unresolved_fixture_links=2) == PARTIAL_FIXTURE_REMEDIATION_REQUIRED
    assert revised_breadth_status(provider_available=True, identity_collisions=1) == LEAGUE_LEVEL_BLOCKER
    assert revised_breadth_status(provider_available=True, material_venue_contradictions=1) == LEAGUE_LEVEL_BLOCKER
    assert revised_breadth_status(provider_available=False) == LEAGUE_LEVEL_BLOCKER
