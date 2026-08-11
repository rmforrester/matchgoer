import requests
import psycopg2


API_KEY = "ff239cf358b6b099d0c75212c24a3e9f"

HEADERS = {
    "x-apisports-key": API_KEY
}


DB = {
    "host": "localhost",
    "database": "football_finder",
    "user": "postgres",
    "password": "Spurley3!",
    "port": 5432
}


LEAGUES = {
    39: "Premier League",
    40: "Championship",
    41: "League One",
    42: "League Two",
    43: "National League"
}


SEASON = 2026


def get_fixtures(league_id, season):

    url = "https://v3.football.api-sports.io/fixtures"

    params = {
        "league": league_id,
        "season": SEASON
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params
    )

    data = response.json()

    if data.get("errors"):
        print(data["errors"])
        return []

    return data["response"]



def get_venue_id(cursor, venue_name):

    if not venue_name:
        return None

    # exact match
    cursor.execute(
        """
        SELECT venue_id
        FROM venues
        WHERE LOWER(name)=LOWER(%s)
        LIMIT 1
        """,
        (venue_name,)
    )

    result = cursor.fetchone()

    if result:
        return result[0]


    # remove punctuation / apostrophes
    clean_name = (
        venue_name
        .lower()
        .replace("'", "")
        .replace("-", " ")
    )


    cursor.execute(
        """
        SELECT venue_id
        FROM venues
        WHERE LOWER(
            REPLACE(
                REPLACE(name, '''', ''),
                '-',
                ' '
            )
        ) = %s
        LIMIT 1
        """,
        (clean_name,)
    )

    result = cursor.fetchone()

    if result:
        return result[0]


    # partial match
    cursor.execute(
        """
        SELECT venue_id
        FROM venues
        WHERE LOWER(name) LIKE %s
        LIMIT 1
        """,
        (f"%{venue_name.lower()}%",)
    )

    result = cursor.fetchone()

    if result:
        return result[0]


    return None



conn = psycopg2.connect(**DB)

cursor = conn.cursor()


total_inserted = 0
missing_venues = 0



for league_id, league_name in LEAGUES.items():

    print("--------------------------------")
    print(f"Loading {league_name}")


fixtures = get_fixtures(
    league_id,
    season=2026
)


print(f"API returned {len(fixtures)} fixtures")


for item in fixtures:


        fixture = item["fixture"]
        league = item["league"]
        teams = item["teams"]
        goals = item["goals"]


        venue = fixture.get("venue") or {}


        venue_name = venue.get("name")
        venue_city = venue.get("city")


        venue_id = get_venue_id(
            cursor,
            venue_name
        )


        if venue_id is None:
            missing_venues += 1



        cursor.execute(
            """
            INSERT INTO fixtures
            (
                fixture_id,
                fixture_date,
                venue_id,
                venue_name,
                venue_city,
                league_id,
                league_name,
                country,
                season,
                round,
                status,
                home_team_id,
                home_team,
                away_team_id,
                away_team,
                home_goals,
                away_goals
            )

            VALUES
            (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s
            )

            ON CONFLICT (fixture_id)
            DO NOTHING
            """,

            (
                fixture["id"],
                fixture["date"][:19],
                venue_id,
                venue_name,
                venue_city,

                league["id"],
                league["name"],
                "England",
                SEASON,

                league.get("round"),

                fixture["status"]["short"],

                teams["home"]["id"],
                teams["home"]["name"],

                teams["away"]["id"],
                teams["away"]["name"],

                goals["home"],
                goals["away"]
            )
        )


        total_inserted += cursor.rowcount



conn.commit()



print("")
print("==============================")
print(f"Inserted fixtures: {total_inserted}")
print(f"Missing venues: {missing_venues}")
print("==============================")


cursor.close()
conn.close()