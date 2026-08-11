# Football Finder - Database Pipeline

## Overview

Football Finder uses API-Football as the source for football fixtures and stadium data.

Current database flow:

API-Football
    |
    ↓
Fixtures Loader
    |
    ↓
PostgreSQL
    |
    ├── fixtures
    |
    ├── teams
    |
    └── venues


## Tables

### fixtures

Stores every football match.

Columns:

- fixture_id
- fixture_date
- venue_id
- venue_name
- venue_city
- league_id
- league_name
- country
- season
- round
- status
- home_team_id
- home_team
- away_team_id
- away_team
- home_goals
- away_goals


### teams

Master list of football teams.

Columns:

- team_id
- team_name
- active
- venue_id


Relationship:

teams.venue_id → venues.venue_id


### venues

Master stadium database.

Columns:

- venue_id
- name
- address
- city
- country
- capacity
- latitude
- longitude


## Current Supported Leagues

England:

| League | API ID |
|---|---:|
| Premier League | 39 |
| Championship | 40 |
| League One | 41 |
| League Two | 42 |
| National League | 43 |


## Current Season

2026/27


## Fixture Loading Process

1. Pull fixtures from API-Football

Endpoint:

fixtures?league={league_id}&season=2026


2. Insert fixtures

3. Extract unique teams

4. Insert new teams

5. Match teams to venues

6. Add missing venues


## Future League Expansion

To add a new league:

1. Add league ID to configuration

Example:

Spain La Liga:
140

MLS:
253


2. Run fixture loader

3. Review unmatched venues

4. Add missing venue records

5. Update team venue relationships


## Data Quality Checks

Before production:

Check missing venues:

SELECT COUNT(*)
FROM teams
WHERE venue_id IS NULL;


Check missing fixture teams:

SELECT COUNT(*)
FROM fixtures
WHERE home_team_id IS NULL
OR away_team_id IS NULL;


Check missing coordinates:

SELECT COUNT(*)
FROM venues
WHERE latitude IS NULL
OR longitude IS NULL;


Expected:

All checks = 0