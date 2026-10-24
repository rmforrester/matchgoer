"""Snapshot validation and public presentation. Never calls a provider."""
import hashlib
import json
from datetime import timezone

from models import Fixture, FixtureEventSnapshot

MAX_EVENTS = 300
MAX_BYTES = 128 * 1024
SCORING = {"Normal Goal": "goal", "Penalty": "penalty", "Own Goal": "own_goal"}
KINDS = {**SCORING, "Missed Penalty": "missed_penalty", "Red Card": "red_card"}
SECOND_YELLOW = {"Second Yellow card", "Second Yellow Card", "Yellow-Red Card"}


def _identity(fixture):
    return {k: getattr(fixture, k) for k in ("fixture_id", "league_id", "season", "home_team_id", "away_team_id")}


def _nonnegative(value):
    return type(value) is int and value >= 0


def snapshot_payload(row):
    """Discard heavy lineups/statistics, preserving original nullable event fields."""
    return {key: row.get(key) for key in ("fixture", "league", "teams", "goals", "score", "events")}


def project_highlights(fixture, payload):
    """Fail closed on identity, score or unsupported period semantics; nulls remain null."""
    try:
        if fixture.status != "FT" or payload["fixture"]["status"]["short"] != "FT":
            return None  # AET/PEN are deferred until authentic period/shootout samples exist.
        expected = _identity(fixture)
        actual = dict(fixture_id=payload["fixture"]["id"], league_id=payload["league"]["id"],
                      season=payload["league"]["season"], home_team_id=payload["teams"]["home"]["id"],
                      away_team_id=payload["teams"]["away"]["id"])
        if actual != expected or any(not _nonnegative(v) for v in actual.values()):
            return None
        if actual["home_team_id"] == actual["away_team_id"]:
            return None
        scores = {"home": fixture.home_goals, "away": fixture.away_goals}
        if any(not _nonnegative(v) for v in scores.values()) or payload["goals"] != scores or payload["score"]["fulltime"] != scores:
            return None
        if any(not _nonnegative(payload[key][side]) for key in ("goals",) for side in scores):
            return None
        source = payload["events"]
        if not isinstance(source, list) or len(source) > MAX_EVENTS or len(json.dumps(payload).encode()) > MAX_BYTES:
            return None
        # Explicit second-yellow records (including paired generic reds) are deferred.
        deferred = {(e.get("team", {}).get("id"), e.get("player", {}).get("id")) for e in source
                    if e.get("type") == "Card" and e.get("detail") in SECOND_YELLOW}
        yellow_counts = {}
        for event in source:
            if event.get("type") == "Card" and event.get("detail") == "Yellow Card":
                player_key = (event.get("team", {}).get("id"), event.get("player", {}).get("id"))
                yellow_counts[player_key] = yellow_counts.get(player_key, 0) + 1
        deferred.update(key for key, count in yellow_counts.items() if count >= 2)
        events, seen, counts, partial = [], set(), {"home": 0, "away": 0}, False
        for index, event in enumerate(source):
            category, detail = event.get("type"), event.get("detail")
            if not ((category == "Goal" and detail in SCORING.keys() | {"Missed Penalty"}) or (category == "Card" and detail == "Red Card")):
                if category == "Goal":
                    return None  # Unknown scoring semantics must not silently reconcile.
                continue
            team_id = event.get("team", {}).get("id")
            if not _nonnegative(team_id):
                return None
            side = next((side for side in scores if actual[side + "_team_id"] == team_id), None)
            if side is None:
                return None
            if detail == "Red Card" and (team_id, event.get("player", {}).get("id")) in deferred:
                partial = True
                continue
            signature = json.dumps(event, sort_keys=True, separators=(",", ":"))
            if signature in seen:
                partial = True
                continue
            seen.add(signature)
            if detail in SCORING:
                counts[side] += 1  # Own-goal event.team is the credited/benefiting side.
            minute = event.get("time", {}).get("elapsed")
            extra = event.get("time", {}).get("extra")
            if minute is not None and (not _nonnegative(minute) or minute > 150):
                return None
            if extra is not None and (not _nonnegative(extra) or extra > 60 or minute is None):
                return None
            player = event.get("player", {}).get("name")
            assist = event.get("assist", {}).get("name") if detail in SCORING else None
            if player is not None and (not isinstance(player, str) or len(player) > 200):
                return None
            if assist is not None and (not isinstance(assist, str) or len(assist) > 200):
                return None
            partial |= not player or minute is None
            events.append(dict(kind=KINDS[detail], minute=minute, extra=extra, player=player,
                               team=fixture.home_team if side == "home" else fixture.away_team,
                               assist=assist, order=index))
        if counts != scores or not events:
            return None
        events.sort(key=lambda e: (e["minute"] if e["minute"] is not None else 1000, e["extra"] or 0, e["order"]))
        return {"events": [{k: v for k, v in e.items() if k != "order"} for e in events],
                "partial": bool(partial), "score_reconciled": True}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def save_snapshot(db, fixture_id, row, fetched_at):
    """Caller owns the transaction. Serialise writers on the existing fixture row."""
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be timezone aware")
    fixture = db.query(Fixture).filter(Fixture.fixture_id == fixture_id).with_for_update().first()
    if fixture is None:
        return False
    payload = snapshot_payload(row)
    if project_highlights(fixture, payload) is None:
        return False  # Preserve an earlier valid snapshot on incomplete/mismatched fetch.
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = db.get(FixtureEventSnapshot, fixture_id)
    if existing:
        previous = existing.fetched_at
        if previous.tzinfo is None:  # SQLite tests; production is timestamptz.
            previous = previous.replace(tzinfo=timezone.utc)
        if previous >= fetched_at:
            return False
        existing.payload, existing.source_sha256, existing.fetched_at = payload, fingerprint, fetched_at
    else:
        db.add(FixtureEventSnapshot(fixture_id=fixture_id, payload=payload, source_sha256=fingerprint, fetched_at=fetched_at))
    db.flush()
    return True


def fixture_highlights(db, fixture):
    if fixture.status != "FT":
        return None
    snapshot = db.get(FixtureEventSnapshot, fixture.fixture_id)
    return project_highlights(fixture, snapshot.payload) if snapshot else None
