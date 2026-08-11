import psycopg2
import re


DB = {
    "host": "localhost",
    "database": "football_finder",
    "user": "postgres",
    "password": "Spurley3!",
    "port": 5432
}


def clean_name(name):
    if not name:
        return ""

    name = name.lower()

    remove_words = [
        "stadium",
        "arena",
        "ground",
        "the",
        "fc",
        "football",
        "community"
    ]

    for word in remove_words:
        name = name.replace(word, "")

    name = re.sub(r"[^a-z0-9]", "", name)

    return name


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
AND venue_name IS NOT NULL
""")


missing = cursor.fetchall()


print("Missing:", len(missing))


# load venues into memory

cursor.execute("""
SELECT 
    venue_id,
    name,
    city
FROM venues
""")


venues = cursor.fetchall()


matched = 0


for fixture_id, venue_name, venue_city in missing:

    fixture_clean = clean_name(venue_name)

    best_match = None


    for venue_id, name, city in venues:

        venue_clean = clean_name(name)


        # name match
        if fixture_clean and (
            fixture_clean in venue_clean
            or venue_clean in fixture_clean
        ):
            best_match = venue_id
            break


        # city backup match
        if venue_city and city:
            if venue_city.lower() == city.lower():
                if len(fixture_clean) > 5:
                    if fixture_clean[:5] in venue_clean:
                        best_match = venue_id
                        break


    if best_match:

        cursor.execute("""
        UPDATE fixtures
        SET venue_id = %s
        WHERE fixture_id = %s
        """,
        (
            best_match,
            fixture_id
        ))

        matched += 1


conn.commit()


print("Updated:", matched)


cursor.close()
conn.close()