import requests

API_KEY = "ff239cf358b6b099d0c75212c24a3e9f"

headers = {
    "x-apisports-key": API_KEY
}

url = "https://v3.football.api-sports.io/leagues?country=england&season=2026"

response = requests.get(
    url,
    headers=headers
)

print(response.json())