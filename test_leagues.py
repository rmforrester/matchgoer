import os
import requests

API_KEY = os.environ["API_FOOTBALL_KEY"]

headers = {
    "x-apisports-key": API_KEY
}

url = "https://v3.football.api-sports.io/leagues?country=england&season=2026"

response = requests.get(
    url,
    headers=headers
)

print(response.json())