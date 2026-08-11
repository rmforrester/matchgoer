import requests

API_KEY = "ff239cf358b6b099d0c75212c24a3e9f"

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