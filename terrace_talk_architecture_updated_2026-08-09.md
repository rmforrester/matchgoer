# Terrace Talk --- Architecture & MVP Roadmap

> **Historical document — superseded 14 August 2026.** See [`docs/architecture.md`](docs/architecture.md) and [`docs/mvp.md`](docs/mvp.md) for canonical current documentation.

**Last updated:** 9 August 2026\
**Status:** Non-production MVP / proof of concept

## 1. Current Product Direction

Terrace Talk is being built around helping football fans discover
away-day opportunities and build a personal stadium-visit history.

The MVP priority is now explicit: **a stadium visit is the primary user
action**.

For MVP, a user records **one visit per stadium**. Multiple
visits/events at the same stadium are deliberately deferred.

Reviews are a secondary layer that can be added after a stadium has been
logged.

This also provides the foundation for future gamification such as: - All
Premier League stadiums - All UK national stadiums - X stadiums over
50,000 capacity - Other competition, country, capacity and stadium-count
badges

## 2. Current Architecture

``` text
Next.js Web App (localhost:3000)
          |
        Axios
          |  credentials / cookies
          v
FastAPI Backend (localhost:8000)
          |
       SQLAlchemy
          v
PostgreSQL

Core domains:
Users / Anonymous Sessions
        |
        v
Stadium Visits / Away Day Reviews
        |        |       Venue  Optional Fixture

Fixtures -> Venues
Interested Fixtures -> Fixtures
Matchday Tips -> Venues
```

### Frontend

Current frontend is a Next.js App Router application using
TypeScript/TSX.

Primary stadium-history route: - `/my-stadiums`

The page is being used as the main stadium-history experience and
contains the Add Stadium search/selection flow.

### Backend

FastAPI + SQLAlchemy.

Current important endpoints include: - `/fixtures` - `/venues` -
`/venues/search` - `/venue/{venue_id}` - `/venues/{venue_id}/fixtures` -
`/nearby` - `/leagues` - `/session` - `/my-reviews` -
`/venues/{venue_id}/away-day-reviews` -
`/venues/{venue_id}/away-day-score` -
`/fixtures/{fixture_id}/interested` - `/interested` - `/tips`

### Database

PostgreSQL accessed through SQLAlchemy.

Core entities currently include: - `User` - `AnonymousSession` -
`Venue` - `Fixture` - `AwayDayReview` - `InterestedFixture` -
`MatchdayTip`

## 3. Stadium Visit Model

The existing `AwayDayReview` table is currently serving as the user's
stadium-visit record.

Relevant fields include:

``` text
review_id
user_id
venue_id
fixture_id       nullable
visit_date       nullable
recommend
overall_score    nullable
atmosphere_score nullable
pubs_score       nullable
getting_there_score nullable
facilities_score nullable
created_at
```

The key MVP relationship is:

``` text
User -> Venue
       one logged visit
```

The backend prevents the same user from adding the same venue twice and
returns HTTP 409 for duplicates.

The intended UX is:

``` text
New stadium
  -> Add to My Stadiums
  -> Visit created

Existing stadium
  -> ✓ Added
  -> Duplicate submission prevented
```

## 4. Anonymous Session Architecture

The MVP currently supports anonymous users.

`GET /session`: 1. Checks for the `terrace_session` cookie. 2. Reuses
the associated anonymous user when present. 3. Creates a new anonymous
`User` and `AnonymousSession` when required. 4. Sets the session cookie.

User-specific endpoints use that session to identify the current user.

This was important during today's testing because the Swagger test user
and browser session user were initially different. The browser session
used for testing was user ID 53.

The session, not a hard-coded user ID, is the source of truth for the
current browser user.

## 5. `/my-reviews`

`GET /my-reviews` now resolves the current anonymous session and returns
only records belonging to that user's stadium history.

Returned data includes:

``` text
review_id
venue_id
venue_name
venue_city
fixture_id
fixture_date
home_team
away_team
visit_date
recommend
overall_score
atmosphere_score
pubs_score
getting_there_score
facilities_score
created_at
```

The endpoint is currently the data source for the user's stadium
history.

## 6. Venue Search

Venue search has been tested successfully through Swagger and the
frontend.

Current behaviour: - Search by stadium/venue name - Search by city -
Limit results - Queries shorter than two characters return no results

Frontend call:

``` text
GET /venues/search?q={query}&limit=20
```

## 7. Stadium Visit Flow

Current intended flow:

``` text
/my-stadiums
      |
      v
Search stadium
      |
      v
Select venue
      |
      +--> Already visited? -> ✓ Added
      |
      +--> New stadium
              |
              v
       Optional visit date
              |
              v
      Add to My Stadiums
              |
              v
        Visit created
```

The backend remains the final source of truth for duplicate protection.

The frontend should show the duplicate state before submission where
possible.

## 8. Review Model

The product model is now:

``` text
STADIUM VISIT
      |
      +--> Review (optional)
             |
             +-- Overall
             +-- Atmosphere
             +-- Pubs/restaurants
             +-- Getting there
             +-- Facilities
             +-- Recommend
```

A stadium can therefore be: - Visited + not reviewed - Visited +
reviewed

The UI should clearly distinguish these states.

The review UI itself is not yet complete.

## 9. Work Completed on 9 August 2026

### Working / verified

-   FastAPI server
-   Swagger/OpenAPI
-   PostgreSQL
-   SQLAlchemy
-   Venue lookup
-   Venue search
-   Fixture lookup
-   Venue fixture lookup
-   Anonymous session creation/reuse
-   `/session`
-   `/my-reviews`
-   Stadium visit creation
-   Duplicate stadium prevention
-   HTTP 409 duplicate response
-   Frontend venue search
-   Frontend Add Stadium flow
-   Browser/API credentials and session-cookie flow

### Problems resolved

**Missing `/session`:** frontend initially received 404. The session
endpoint was implemented.

**`/my-reviews` 500:** existing visit records had `recommend = NULL`
while the response model expected a boolean. The response model/data
handling was adjusted so existing visit records can be returned.

**Wrong user/session:** Swagger and browser were using different users.
The architecture was corrected to use the browser session as the current
user.

**Duplicate stadiums:** SQL and API testing confirmed that the same user
cannot add the same venue twice.

**Frontend duplicate UX:** the frontend is being changed to show
`✓ Added` rather than relying on a failed duplicate request.

**My Stadiums rendering:** the backend was already returning stadium
records, but the frontend was only rendering the Add Stadium section.
The next frontend change is to render the user's stadium list above Add
Stadium.

## 10. Next Sprints

### Sprint 1 --- Finish My Stadiums

**Highest priority.**

Goal: make stadium visit tracking fully usable end-to-end.

Tasks: 1. Confirm `/my-stadiums` displays logged stadiums. 2. Show
stadium name and city. 3. Show visited status. 4. Show visit date when
available. 5. Distinguish visited + reviewed from visited + not
reviewed. 6. Finalise Add Stadium UX. 7. Confirm persistence after
refresh. 8. Remove unused/duplicate Add Stadium page if no longer
needed. 9. Remove temporary test code.

**Definition of done:** a user can search for a stadium, add it once,
refresh the page and see it permanently listed in My Stadiums.

### Sprint 2 --- Stadium Reviews

Goal: allow a user to review a stadium they have already visited.

Tasks: 1. Add Review Stadium action. 2. Build review form. 3. Validate
score ranges. 4. Save review. 5. Display review score on My Stadiums. 6.
Test visit -\> review end-to-end.

### Sprint 3 --- Stadium Detail

Potential route:

``` text
/venues/{venue_id}
```

Show: - Stadium name - City - Coordinates - Capacity - Team/club
information - Fixtures - Away Day score - User's visit status - User's
review - Other useful venue information

### Sprint 4 --- Fixtures + Away-Day Discovery

Connect existing fixture functionality to the personal stadium
experience.

Tasks: 1. Improve fixture browsing. 2. Connect fixtures to venue pages.
3. Connect interested fixtures to the user session. 4. Add clear
visit-state indicators. 5. Use venue + fixture data to support away-day
planning.

### Sprint 5 --- Stadium Gamification

Turn the stadium log into a retention feature.

Initial metrics:

``` text
Stadiums visited: X

Premier League stadiums: X / 20

50,000+ capacity: X

UK national stadiums: X / Y
```

Initial badge concepts: - First Stadium - 10 Stadiums - 25 Stadiums - 50
Stadiums - 100 Stadiums - All Premier League Stadiums - All UK National
Stadiums - 5 Stadiums over 50k - 10 Stadiums over 50k

Badge logic should be data-driven from venue metadata and user stadium
history.

### Sprint 6 --- Venue Data Quality

Improve venue metadata before relying heavily on gamification.

Useful fields: - Capacity - Country - Nation/home association - City -
Latitude - Longitude - Stadium status - Club/team - League/competition
associations

### Sprint 7 --- Production Hardening

After the core MVP loop is working: - Authentication strategy -
Persistent accounts - Database constraints/indexes - API
validation/error handling - Logging - Automated tests - Rate limiting -
Environment variables/secrets - Production CORS - Deployment - Backups -
Monitoring

## 11. Recommended Build Order

``` text
1. Venue + Fixture data
        |
2. Anonymous session
        |
3. Stadium visit logging
        |
4. My Stadiums
        |
5. Stadium reviews
        |
6. Stadium detail pages
        |
7. Fixture / away-day discovery
        |
8. Gamification / badges
        |
9. Account system
        |
10. Production hardening
```

The key product principle is:

> Do not overbuild the review system before the stadium-visit system is
> excellent.

The stadium collection/history is the primary MVP user-value loop.

## 12. Architecture Principles

### Stadium visit is the canonical user activity

A user visiting a stadium creates one persistent user-to-venue
relationship.

### Reviews are secondary

Reviews enrich a visit but do not define whether the user has visited
the stadium.

### Fixtures are optional context

A user should eventually be able to associate a visit with a fixture,
but a fixture is not required to log a stadium.

### Backend owns business rules

Frontend provides the UX; backend owns duplicate prevention and data
integrity.

### Session determines current user

Do not hard-code user IDs in frontend/API logic.

### Badges should be data-driven

Achievement logic should be calculated from structured venue metadata
and the user's stadium history.

### Build incrementally

Use:

``` text
Database
   ->
API
   ->
Swagger test
   ->
Frontend
   ->
End-to-end test
```

## Current End State

As of 9 August 2026, Terrace Talk has moved beyond the initial data/API
proof of concept and now has the foundations of a genuine personal
stadium-tracking product.

The immediate objective is to complete:

``` text
SEARCH
  ->
SELECT STADIUM
  ->
ADD VISIT
  ->
MY STADIUMS
  ->
REVIEW
```

Once this loop is reliable, the project has a strong foundation for
fixture discovery, away-day planning, and stadium-based gamification.
