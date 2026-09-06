"""Protected England/Germany Before-the-Match destination-only cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import make_url


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Approved recommendations are immutable here. Only these exact destination
# strings may change, and only when their exact prior value is present.
FIXED = {
    4: ("The Phoenix, London", "The Phoenix, Cherry Red Records Stadium, Plough Lane, London SW17 0NR"),
    5: ("South Stand Fan Zone, London", "South Stand Fan Zone, Cherry Red Records Stadium, Plough Lane, London SW17 0NR"),
    94: ("Stadtwaldgarten, Venloer Straße 1031, 50829 Köln", "Stadtwaldgarten, Aachener Straße 701, 50933 Köln"),
}

GROUND_CONTEXT = {
    36: ("Fan Zone", "Turf Moor", "Burnley"),
    37: ("Foster's Fan Zone", "Elland Road", "Leeds, West Yorkshire"),
    38: ("Official Fan Zone", "Toughsheet Community Stadium", "Bolton"),
    39: ("Mel Nurse Bar", "Swansea.com Stadium", "Swansea"),
    40: ("Beacon of Light Fan Zone", "Stadium of Light", "Sunderland"),
    41: ("University of Staffordshire Fan Zone", "Vale Park", "Stoke-on-Trent, Staffordshire"),
    42: ("Croud Meadow FanZone", "The Croud Meadow", "Shrewsbury, Shropshire"),
    43: ("St James Park Fan Zone", "St James Park", "Exeter, Devon"),
    44: ("The Factory", "Priestfield Stadium", "Gillingham, Kent"),
    45: ("Jim's Bar", "Highbury Stadium", "Fleetwood, Lancashire"),
    46: ("Belle Vue Bar", "Eco-Power Stadium", "Doncaster, South Yorkshire"),
    47: ("Koala NW matchday pop-up", "Prenton Park", "Birkenhead, Merseyside"),
    48: ("Fan Zone", "SO Legal Stadium", "Barrow-in-Furness, Cumbria"),
    49: ("Away Fan Zone", "The Bolt New Lawn", "Nailsworth, Gloucestershire"),
    50: ("Bar Twenty Seven", "The Leasing.com Stadium", "Macclesfield, Cheshire"),
    51: ("Daggers Clubhouse", "Chigwell Construction Stadium", "Dagenham, Essex"),
    52: ("The Hangar Bar", "Silverlake Stadium", "Eastleigh, Hampshire"),
    53: ("Heed Army Sports Bar", "Gateshead International Stadium", "Gateshead, Tyne and Wear"),
    54: ("The Glass House", "Meadow Park", "Borehamwood, Hertfordshire"),
    55: ("Fan Zone", "ARMCO Arena", "Solihull, West Midlands"),
    56: ("Fan Zone Bar", "VBS Community Stadium", "Sutton, Surrey"),
    57: ("Fan Zone", "The Laithwaite Community Stadium", "Woking, Surrey"),
    58: ("South Stand Bar", "The Shay Stadium", "Halifax, West Yorkshire"),
    59: ("Beveree Fan Zone", "Beveree Stadium", "Hampton, Middlesex"),
    60: ("Clubhouse Bar", "Melbourne Stadium", "Chelmsford, Essex"),
    61: ("Saints Bar", "Clarence Park", "St. Albans, Hertfordshire"),
    62: ("Clubhouse Bar", "Home Call Carpets Community Stadium", "Burgess Hill, West Sussex"),
    63: ("The Venue and Sports Bar", "AlderSmith Stadium", "Frome, Somerset"),
    64: ("Honeycroft Bar", "Honeycroft", "London"),
    65: ("Bards Fanzone", "Atalian Servest Stadium", "Bury St Edmunds, Suffolk"),
    66: ("Fan Zone", "The Peninsula Stadium", "Salford, Greater Manchester"),
    67: ("County Courtyard", "Edgeley Park", "Stockport, Greater Manchester"),
    68: ("Huish Park Fanzone", "Huish Park Stadium", "Yeovil, Somerset"),
    69: ("Clubhouse Bar", "Nethermoor Park", "Guiseley, West Yorkshire"),
    70: ("Berkhamsted FC Clubhouse", "Broadwater", "Berkhamsted, Hertfordshire"),
    71: ("The Yeltz Bar", "The Grove", "Halesowen, West Midlands"),
    72: ("Chase Suite", "Keys Park", "Hednesford, Staffordshire"),
    73: ("The Rook Inn", "The Dripping Pan", "Lewes, East Sussex"),
    74: ("Webleys Bar", "Penydarren Park", "Merthyr Tydfil"),
    75: ("Fan Zone", "The Lamb Ground", "Tamworth, Staffordshire"),
    76: ("FanZone", "Sussex Transport Community Stadium", "Worthing, West Sussex"),
    77: ("1883 Sports Bar", "New Meadow Park", "Gloucester, Gloucestershire"),
    78: ("Clubhouse Bar", "Your Co-op Community Stadium", "Royal Leamington Spa, Warwickshire"),
    79: ("Angels Sports Bar", "Longmead Stadium", "Tonbridge, Kent"),
    80: ("Clubhouse Bar", "The Memorial Ground Farnham", "Farnham, Surrey"),
    81: ("SDS Fan Zone", "Rectory Meadow", "Hanworth, Middlesex"),
    82: ("The Full Time", "Manadon Sports Hub", "Plymouth, Devon"),
    83: ("Clubhouse Bar", "Townsend Meadow", "Warwick, Warwickshire"),
    84: ("Club Bar", "The Hive Arena", "Warrington, Cheshire"),
    85: ("Blackwell Meadows Clubhouse", "Blackwell Meadows", "Darlington, Durham"),
}

CORRECTIONS = dict(FIXED)
CORRECTIONS.update({spot_id: (name, f"{name}, {ground}, {city}") for spot_id, (name, ground, city) in GROUND_CONTEXT.items()})


def snapshot(connection):
    ids = sorted(CORRECTIONS)
    rows = connection.execute(text("""SELECT pre_match_spot_id,display_name,maps_destination
        FROM pre_match_spots WHERE pre_match_spot_id IN :ids ORDER BY pre_match_spot_id""").bindparams(
        bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    outside = connection.execute(text("""SELECT md5(COALESCE(string_agg(row_to_json(x)::text,'' ORDER BY x.pre_match_spot_id),''))
        FROM (SELECT * FROM pre_match_spots WHERE pre_match_spot_id NOT IN :ids) x""").bindparams(
        bindparam("ids", expanding=True)), {"ids": ids}).scalar_one()
    counts = {name: connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one() for name in (
        "teams", "venues", "fixtures", "club_venues", "venue_guide_facts", "pre_match_spots",
        "pre_match_spot_evidence", "decision_facts", "decision_evidence",
    )}
    return rows, outside, counts


def classify(rows):
    by_id = {row["pre_match_spot_id"]: row for row in rows}
    if set(by_id) != set(CORRECTIONS):
        raise RuntimeError("destination correction identity set drift")
    pending, exact = [], []
    for spot_id, (before, after) in CORRECTIONS.items():
        row = by_id[spot_id]
        if row["maps_destination"] == before:
            pending.append(spot_id)
        elif row["maps_destination"] == after:
            exact.append(spot_id)
        else:
            raise RuntimeError(f"destination drift for spot {spot_id}: {row['maps_destination']!r}")
    return pending, exact


def run(url, write=False):
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        tx = connection.begin()
        try:
            if not write:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            before_rows, before_outside, before_counts = snapshot(connection)
            pending, exact = classify(before_rows)
            if write:
                if exact or len(pending) != len(CORRECTIONS):
                    raise RuntimeError("write requires the complete exact pre-change state")
                for spot_id in pending:
                    before, after = CORRECTIONS[spot_id]
                    result = connection.execute(text("""UPDATE pre_match_spots SET maps_destination=:after
                        WHERE pre_match_spot_id=:spot_id AND maps_destination=:before"""),
                        {"spot_id": spot_id, "before": before, "after": after})
                    if result.rowcount != 1:
                        raise RuntimeError(f"guarded update failed for spot {spot_id}")
                after_rows, after_outside, after_counts = snapshot(connection)
                pending_after, exact_after = classify(after_rows)
                if pending_after or len(exact_after) != len(CORRECTIONS):
                    raise RuntimeError("post-write destination reconciliation failed")
                if before_outside != after_outside or before_counts != after_counts:
                    raise RuntimeError("unrelated state changed")
                tx.commit()
            else:
                tx.rollback()
                after_counts = before_counts
            return {
                "state": "EXACTLY_PRESENT" if write or not pending else "READY",
                "pending": len(pending), "already_correct": len(exact),
                "england_updates": 52, "germany_updates": 1,
                "total_updates": len(CORRECTIONS) if write else 0,
                "deletes": 0, "unrelated_changes": 0,
                "counts": after_counts,
            }
        except Exception:
            if tx.is_active:
                tx.rollback()
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--allow-remote-write", action="store_true")
    parser.add_argument("--expected-script-sha256")
    args = parser.parse_args()
    url = os.environ.get("MATCHGOER_HOSTED_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("database URL is required")
    if args.write:
        actual = hashlib.sha256(open(__file__, "rb").read()).hexdigest().upper()
        if not args.confirm_write or args.expected_script_sha256 != actual:
            raise RuntimeError(f"write requires confirmation and exact script SHA-256 {actual}")
        if make_url(url).host not in LOCAL_HOSTS and not args.allow_remote_write:
            raise RuntimeError("remote write requires --allow-remote-write")
    print(json.dumps(run(url, args.write), indent=2))


if __name__ == "__main__":
    main()
