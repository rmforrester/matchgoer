import requests
import pandas as pd

API_KEY = "ff239cf358b6b099d0c75212c24a3e9f"

url = "https://v3.football.api-sports.io/venues"

headers = {
    "x-apisports-key": API_KEY
}

params = {
    "country": "England"
}

response = requests.get(
    url,
    headers=headers,
    params=params
)

print("Status code:", response.status_code)

data = response.json()

# Check the API response
print("API response keys:", data.keys())
print("Number of venues returned:", len(data.get("response", [])))

# Create clean venue list
venues = []

for venue in data.get("response", []):
    venues.append({
        "venue_id": venue.get("id"),
        "name": venue.get("name"),
        "address": venue.get("address"),
        "city": venue.get("city"),
        "country": venue.get("country"),
        "capacity": venue.get("capacity")
    })

# Convert to dataframe
df = pd.DataFrame(venues)

print(df.head())

# Save CSV
df.to_csv(
    "venues_england_clean.csv",
    index=False
)

print("Created venues_england_clean.csv")