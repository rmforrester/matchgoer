"""Offline replay of public read-only snapshots; exact bounded insert manifests."""
from datetime import datetime
from sqlalchemy import create_engine, text, MetaData, Table


def snapshot_database(data):
    engine=create_engine('sqlite://')
    definitions={
        'fixtures':'fixture_id INTEGER PRIMARY KEY, fixture_date DATETIME, venue_id INTEGER, venue_name TEXT, venue_city TEXT, league_id INTEGER, league_name TEXT, country TEXT, season INTEGER, round TEXT, status TEXT, home_team_id INTEGER, home_team TEXT, away_team_id INTEGER, away_team TEXT, home_goals INTEGER, away_goals INTEGER',
        'teams':'team_id INTEGER PRIMARY KEY, team_name TEXT',
        'venues':'venue_id INTEGER PRIMARY KEY, name TEXT, city TEXT, country TEXT, latitude FLOAT, longitude FLOAT, provider_venue_id INTEGER, canonical_venue_id INTEGER',
        'venue_provider_refs':'venue_id INTEGER, provider TEXT, provider_venue_id INTEGER, valid_to TEXT',
        'venue_names':'venue_id INTEGER, name TEXT, valid_to TEXT',
        'team_identity_overrides':'team_identity_override_id INTEGER PRIMARY KEY, provider TEXT, provider_team_id INTEGER, league_id INTEGER, season INTEGER, canonical_team_id INTEGER, expected_provider_name TEXT, review_status TEXT'}
    with engine.begin() as c:
        for name,definition in definitions.items():
            c.execute(text('CREATE TABLE '+name+' ('+definition+')'))
            table=Table(name,MetaData(),autoload_with=c)
            keys={col.name for col in table.columns}
            rows=[]
            for row in data[name]:
                row={k:v for k,v in row.items() if k in keys}
                if name=='fixtures':row['fixture_date']=datetime.fromisoformat(row['fixture_date'])
                rows.append(row)
            for i in range(0,len(rows),1000):
                c.execute(table.insert(),rows[i:i+1000])
    return engine
