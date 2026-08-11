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
    venue_name,
    venue_city,
    COUNT(*) AS fixtures
FROM fixtures
WHERE season = 2026
AND venue_id IS NULL
GROUP BY venue_name, venue_city
ORDER BY fixtures DESC
LIMIT 50;
""")


rows = cursor.fetchall()


for row in rows:
    print(row)


cursor.close()
conn.close()