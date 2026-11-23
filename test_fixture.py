import os
import requests

API_KEY = os.environ["API_FOOTBALL_KEY"]

headers = {
    "x-apisports-key": API_KEY
}

url = "https://v3.football.api-sports.io/fixtures"

params = {
    "league": 39,
    "season": 2025
}

response = requests.get(
    url,
    headers=headers,
    params=params
)

print(response.url)
print(response.json())