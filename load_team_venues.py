import requests
import psycopg2
import time


# ==========================
# CONFIG
# ==========================

API_KEY = "ff239cf358b6b099d0c75212c24a3e9f"

DB_CONFIG = {
    "host": "localhost",
    "database": "football_finder",
    "user": "postgres",
    "password": "Spurley3!",
    "port": 5432
}


HEADERS = {
    "x-apisports-key": API_KEY
}


# ==========================
# DATABASE CONNECTION
# ==========================

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()


# ==========================
# GET TEAMS
# ==========================

cur.execute("""
    SELECT team_id, team_name
    FROM teams
    WHERE venue_id IS NULL
""")

teams = cur.fetchall()

print(f"Teams needing venues: {len(teams)}")


# ==========================
# PROCESS TEAMS
# ==========================

for team_id, team_name in teams:

    print(f"\nChecking {team_name} ({team_id})")

    url = f"https://v3.football.api-sports.io/teams?id={team_id}"

    response = requests.get(
        url,
        headers=HEADERS
    )

    data = response.json()


    if data.get("results") == 0:
        print("No API result")
        continue


    try:
        venue = data["response"][0]["venue"]

        venue_name = venue["name"]
        venue_city = venue["city"]

        print(
            f"API venue: {venue_name} - {venue_city}"
        )


        # Find venue in database

        cur.execute("""
            SELECT venue_id
            FROM venues
            WHERE LOWER(name) = LOWER(%s)
            OR (
                LOWER(city) = LOWER(%s)
                AND LOWER(name) LIKE LOWER(%s)
            )
            LIMIT 1
        """,
        (
            venue_name,
            venue_city,
            "%" + venue_name + "%"
        ))


        result = cur.fetchone()


        if result:

            venue_id = result[0]

            cur.execute("""
                UPDATE teams
                SET venue_id = %s
                WHERE team_id = %s
            """,
            (
                venue_id,
                team_id
            ))

            conn.commit()

            print(
                f"UPDATED -> venue_id {venue_id}"
            )

        else:

            print(
                "No matching venue found"
            )


    except Exception as e:

        print(
            "Error:",
            e
        )


    # avoid API rate limits
    time.sleep(0.3)



cur.close()
conn.close()

print("\nFinished")