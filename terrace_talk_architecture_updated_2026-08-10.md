# Terrace Talk — Architecture, Current State & MVP Roadmap

> **Historical document — superseded 14 August 2026.** For the current implementation and approved architecture, see [`docs/architecture.md`](docs/architecture.md) and [`docs/mvp.md`](docs/mvp.md). Statements below describe the repository at an earlier point and may now be obsolete.

**Last updated:** 10 August 2026  
**Status:** Non-production MVP / proof of concept  
**Current phase:** Core stadium experience working; discovery/navigation polish next

---

## 1. Product Direction

Terrace Talk is being built to help football fans discover away-day opportunities and build a personal stadium-visit history.

The core product loop is now:

```text
DISCOVER A FIXTURE
       ↓
IDENTIFY THE STADIUM
       ↓
VIEW THE AWAY-DAY EXPERIENCE
       ↓
RECORD THE VISIT
       ↓
REVIEW THE STADIUM
       ↓
SAVE / TRACK FIXTURES OF INTEREST
```

The primary user relationship remains **User → Stadium Visit**. Reviews enrich that relationship rather than defining whether a user has visited a stadium.

For the current MVP, a user records one visit per stadium. Multiple visits/events at the same stadium are deferred.

---

## 2. Current Architecture

```text
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
```

Core domains:

```text
Users / Anonymous Sessions
        |
        +--> Stadium Visits / Away Day Reviews
        |
        +--> Interested Fixtures
        |
        +--> My Stadiums / My Reviews

Fixtures ----> Venues
Fixtures ----> Nearby discovery
Venues ------> Matchday Tips
Venues ------> Away Day Ratings / Reviews
```

### Frontend

The frontend is a Next.js App Router application using TypeScript/TSX.

Important routes/components currently include:

- `/` — fixture discovery homepage
- `/my-stadiums` — personal stadium history / Add Stadium flow
- `/venue/[venueId]` — stadium detail page
- `FixtureMap` — fixture and stadium map experience
- `SearchBar` — fixture discovery filters
- `VenueHeader` — stadium identity
- `AwayDayScore` — community rating display
- `MatchdayTips` — stadium tips

The final navigation linking `/` and `/my-stadiums` is still outstanding and is the last UI task planned for 10 August.

### Backend

FastAPI + SQLAlchemy.

Current important endpoint groups include:

**Core data**

- `GET /`
- `GET /fixtures`
- `GET /venues`
- `GET /venue/{venue_id}`
- `GET /venues/search`
- `GET /venues/{venue_id}/fixtures`
- `GET /leagues`
- `GET /nearby`

**Session / personal data**

- `GET /session`
- `GET /my-reviews`
- `GET /interested`

**Stadium reviews / ratings**

- `POST /venues/{venue_id}/away-day-reviews`
- `PATCH /venues/{venue_id}/away-day-reviews`
- `GET /venues/{venue_id}/away-day-reviews`
- `GET /venues/{venue_id}/away-day-score`

**Interested fixtures**

- `POST /fixtures/{fixture_id}/interested`
- `DELETE /fixtures/{fixture_id}/interested`
- `GET /interested`

**Matchday tips**

- `POST /tips`
- `GET /venues/{venue_id}/tips`
- `POST /tips/{tip_id}/helpful`
- `POST /tips/{tip_id}/report`

### Database

PostgreSQL accessed through SQLAlchemy.

Core entities currently include:

- `User`
- `AnonymousSession`
- `Venue`
- `Fixture`
- `AwayDayReview`
- `InterestedFixture`
- `MatchdayTip`

---

## 3. Anonymous Session Architecture

The MVP currently supports anonymous users.

`GET /session`:

1. Checks for the `terrace_session` cookie.
2. Reuses the associated anonymous user when present.
3. Creates a new anonymous `User` and `AnonymousSession` when required.
4. Sets/reuses the session cookie.

The frontend Axios client uses credentials so the browser session is sent to the backend.

The session, not a hard-coded user ID, is the source of truth for the current browser user.

This was tested on direct refreshes of venue pages and is now working as intended.

---

## 4. Stadium Visit / My Stadiums

The existing `AwayDayReview` table is currently serving as the user's stadium-visit record.

Relevant fields include:

```text
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

The key relationship is:

```text
User -> Venue
       one logged visit
```

The backend prevents the same user from adding the same venue twice and returns HTTP 409 for duplicate submissions.

Current visit states are:

```text
Not visited
    ↓
Visited / not reviewed
    ↓
Visited / reviewed
```

The frontend distinguishes these states and provides review/edit actions where appropriate.

### My Stadiums status

The core My Stadiums flow is working:

- Search for a stadium
- Select a stadium
- Add it to My Stadiums
- Prevent duplicate visits
- Persist the visit
- Refresh and retain the visit
- Show visited state
- Link into the stadium experience

Remaining polish includes cleanup of temporary/development UI and improving cross-page navigation.

---

## 5. Stadium Detail Page

The stadium detail page is now a substantial MVP feature at:

```text
/venue/{venueId}
```

It currently provides:

### Venue information

- Stadium name
- City
- Country
- Capacity

### Personal state

- Add to My Stadiums
- Visited state
- Review state
- Edit review
- User's Terrace Rating

### Community ratings

**Terrace Rating** — the overall supporter score.

**Away Day Rating** — percentage of reviewers who would recommend the away day.

The page also displays the rating breakdown:

- 🥁 Atmosphere
- 🍺 Pubs & Restaurants
- 🚆 Getting There
- 🏟️ Stadium / Food / Facilities

### Rating model

The overall score is calculated from the completed category scores rather than assuming every category has been completed.

A review can therefore contain partial category data.

The current UI displays the user's own rating separately from the community rating.

---

## 6. Reviews

A stadium review can contain:

- Overall score
- Atmosphere score
- Pubs/restaurants score
- Getting there score
- Facilities score
- Recommend

The review API supports creation and updates.

The product language now uses:

```text
Terrace Rating
Away Day Rating
Your Terrace Rating
```

This gives the product two distinct community signals without duplicating the full rating breakdown throughout the UI.

### Review threshold

A venue can display community ratings when there is at least one review.

The product does not require five reviews before showing the rating. Low review counts are implicitly treated as early/limited data rather than hidden.

---

## 7. Matchday Tips

Venue pages support community matchday tips.

Current functionality includes:

- Add a tip
- View venue tips
- Helpful voting
- Reporting
- Report/status handling

Further moderation and abuse-prevention work is deferred until after the core MVP loop is complete.

---

## 8. Fixtures & Away-Day Discovery

Fixture functionality is working at both general and venue-specific levels.

Current fixture data includes:

- Fixture ID
- Date
- Home team
- Away team
- League
- Venue
- Venue coordinates
- Distance from the user for nearby searches

The homepage supports:

- Location
- Radius
- Start date
- End date
- League
- Nearby fixture search
- Map display
- Fixture cards
- Interested state

The venue page now also displays upcoming fixtures for that stadium.

### Venue fixture cards

Upcoming venue fixtures currently show:

- Date
- Teams
- Stadium
- `X Terrace Talk users interested`
- Current user's Interested state

The Interested action can be toggled on and off without refreshing the page, and the community count updates immediately.

The venue page intentionally does **not** repeat the Terrace Rating/Away Day Rating on every fixture card because those scores are already displayed in the main stadium experience.

### Outstanding discovery work

The homepage still needs further product polish so that fixture discovery more clearly communicates the full Terrace Talk value proposition.

A future improvement is to surface community interest and potentially stadium ratings on homepage fixture cards. Those signals should not be duplicated unnecessarily on the venue page.

---

## 9. Map Experience

The map uses Leaflet via `react-leaflet`.

Current map behaviour includes:

- Fixture pins
- Stadium pins
- Different visual meaning for fixtures vs stadiums
- Visited stadium indicators
- Fixture popups
- Stadium popups
- Venue navigation
- Distance information

The agreed visual logic is:

```text
⚽ Football icon = fixture occurring
🔵 Blue stadium pin = stadium
```

Visited stadiums receive a visited indicator.

---

## 10. Interested Fixtures

The interested-fixture system is now working end-to-end.

Current endpoints:

```text
POST   /fixtures/{fixture_id}/interested
DELETE /fixtures/{fixture_id}/interested
GET    /interested
```

The system is session-aware and therefore tracks interest per anonymous Terrace Talk user.

Venue fixture cards also expose the aggregate community count:

```text
12 Terrace Talk users interested
```

The count increments/decrements immediately when the current user toggles their own interest.

### Technical note

The current venue-fixture implementation calculates interested counts per fixture. This is appropriate for the MVP prototype. A grouped SQL query can replace the per-fixture count later if scale requires it.

---

## 11. Current User Journey

The current product journey is now:

```text
HOME
  |
  | Find nearby fixtures
  v
FIXTURE / MAP
  |
  | Select stadium
  v
STADIUM PAGE
  |
  +--> View Terrace Rating
  |
  +--> View Away Day Rating
  |
  +--> View tips
  |
  +--> View upcoming fixtures
  |
  +--> Mark fixture Interested
  |
  +--> Add stadium / see visited state
  |
  +--> Create or edit review
  |
  v
MY STADIUMS
```

The remaining missing piece in this journey is simple global navigation between the homepage and My Stadiums.

---

## 12. Work Completed — 10 August 2026

### Backend / infrastructure

- FastAPI server
- Swagger/OpenAPI
- PostgreSQL
- SQLAlchemy
- Venue lookup
- Venue search
- Fixture lookup
- Venue fixture lookup
- Nearby fixture search
- League lookup
- Anonymous session creation/reuse
- Session cookie persistence
- Browser/API credentials flow

### Stadium tracking

- Add stadium
- Persistent visit record
- Duplicate stadium prevention
- HTTP 409 duplicate handling
- My Stadiums
- Visited state
- Reviewed vs not reviewed state
- Review editing

### Stadium experience

- Stadium detail page
- Terrace Rating
- Away Day Rating
- Personal Terrace Rating
- Category rating breakdown
- Matchday Tips
- Upcoming fixtures
- Community Interested count
- Interested toggle

### Map

- Fixture pins
- Stadium pins
- Visited stadium indicators
- Fixture/stadium popup information
- Venue navigation

### Problems resolved during development

- Missing `/session`
- Incorrect browser/Swagger session separation
- `/my-reviews` null/recommend handling
- Duplicate stadium submissions
- Venue ID mismatch errors on review creation
- Missing/incorrect review display on venue pages
- Incorrect score aggregation when categories are incomplete
- Fixture map visited-state issues
- Stadium pins vs fixture pins
- Interested toggle behaviour
- Session loss on direct venue-page refresh
- Venue-page UI duplication / rating presentation issues

---

## 13. Immediate Remaining Work

### Final task for 10 August — Global navigation

Add simple navigation so users can move between:

```text
Terrace Talk / Home
        ↕
   My Stadiums
```

This should be a small, reusable navigation element rather than separate buttons implemented independently on each page.

### After navigation — Define MVP

Once navigation is complete, stop feature development and formally define the MVP.

The MVP definition should specify:

- Target user
- Core problem
- Core user journey
- Must-have features
- Features explicitly excluded from MVP
- MVP definition of done
- Basic user testing scenarios

---

## 14. Post-MVP Roadmap

### Phase 2 — Discovery improvements

- Improve homepage fixture cards
- Surface community interest on nearby fixtures
- Improve search/filter UX
- Improve fixture-to-stadium navigation
- Improve map/list interaction
- Add stronger away-day planning context

### Phase 3 — Gamification / retention

Potential metrics:

```text
Stadiums visited: X
Premier League stadiums: X / 20
50,000+ capacity: X
UK national stadiums: X / Y
```

Potential badges:

- First Stadium
- 10 Stadiums
- 25 Stadiums
- 50 Stadiums
- 100 Stadiums
- All Premier League Stadiums
- All UK National Stadiums
- 5 Stadiums over 50k
- 10 Stadiums over 50k

Badge logic should be data-driven from venue metadata and stadium history.

### Phase 4 — Accounts

- Registration
- Login
- Persistent account identity
- Anonymous-to-account migration
- Profile

### Phase 5 — Production hardening

- Production database
- Environment variables / secrets
- Production CORS
- Authentication strategy
- Database constraints/indexes
- API validation/error handling
- Automated tests
- Rate limiting
- Logging
- Monitoring
- Backups
- Deployment
- Analytics

---

## 15. Known Technical Debt / Deferred Work

The following are deliberately deferred rather than treated as MVP blockers:

- Production authentication
- Production deployment
- Automated test suite
- Rate limiting
- Advanced moderation
- Optimised interested-count SQL
- Multiple visits to the same stadium
- Full fixture detail pages
- Advanced gamification
- Complete venue metadata enrichment
- Production analytics/monitoring
- Removal of all temporary development/test configuration

The current test location in the homepage is still development configuration and must be removed or disabled before production use.

---

## 16. Architecture Principles

### Stadium visit is the canonical user activity

A user visiting a stadium creates the primary persistent user-to-venue relationship.

### Reviews are secondary

Reviews enrich a visit but do not define whether the user has visited the stadium.

### Fixtures provide discovery/context

Fixtures help users discover away-day opportunities and can be associated with a visit, but a fixture is not required to record a stadium visit.

### Backend owns business rules

Frontend provides the UX; backend owns duplicate prevention, session identity and data integrity.

### Session determines current user

Do not hard-code user IDs in frontend/API logic.

### Build incrementally

Use:

```text
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

### Avoid feature sprawl

The next feature should strengthen the core discovery → stadium → visit/review loop before introducing a new major product surface.

---

## 17. MVP Definition — To Be Finalised

The MVP should be formally defined after the final homepage/My Stadiums navigation task is complete.

Current working definition:

> **Terrace Talk is a football away-day discovery and stadium-tracking product that lets a fan find nearby fixtures, explore the stadium experience, record stadium visits, review stadiums and track fixtures they are interested in.**

The formal MVP definition of done will be agreed next, before further feature development.

---

## Current End State

Terrace Talk has moved beyond the initial data/API proof of concept and now has a functioning end-to-end stadium experience.

The product currently has enough functionality to put in front of a small group of users for qualitative feedback once the final global navigation is added.

The immediate sequence is:

```text
1. Add Home <-> My Stadiums navigation
             ↓
2. Define and freeze MVP scope
             ↓
3. Put prototype in front of users
             ↓
4. Gather feedback
             ↓
5. Prioritise post-MVP improvements
```
