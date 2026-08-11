import psycopg2


DB = {
    "host": "localhost",
    "database": "football_finder",
    "user": "postgres",
    "password": "Spurley3!",
    "port": 5432
}


conn = psycopg2.connect(**DB)
cursor = conn.cursor()


cursor.execute("""
SELECT 
    fixture_id,
    venue_name,
    venue_city
FROM fixtures
WHERE season = 2026
AND venue_id IS NULL
""")


missing = cursor.fetchall()


print(f"Missing venues found: {len(missing)}")


matched = 0


for fixture_id, venue_name, venue_city in missing:

    if venue_name is None:
        continue


    cursor.execute(
        """
        SELECT venue_id
        FROM venues
        WHERE LOWER(name) = LOWER(%s)
        LIMIT 1
        """,
        (venue_name,)
    )


    result = cursor.fetchone()


    if result:

        cursor.execute(
            """
            UPDATE fixtures
            SET venue_id = %s
            WHERE fixture_id = %s
            """,
            (
                result[0],
                fixture_id
            )
        )

        matched += 1



conn.commit()


print(f"Matched and updated: {matched}")


cursor.close()
conn.close()