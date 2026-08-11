import requests
import pandas as pd


API_KEY = "ff239cf358b6b099d0c75212c24a3e9f"


headers = {
    "x-apisports-key": API_KEY
}


# England top 5 leagues
leagues = {
    39: "Premier League",
    40: "Championship",
    41: "League One",
    42: "League Two",
    43: "National League"
}


season = 2026


all_fixtures = []


for league_id, league_name in leagues.items():

    print(f"Getting {league_name} fixtures...")

    url = "https://v3.football.api-sports.io/fixtures"

    params = {
        "league": league_id,
        "season": season
    }


    response = requests.get(
        url,
        headers=headers,
        params=params
    )


    data = response.json()


print(league_name)
print(data)
print("-------------------")


for fixture in data["response"]:

        venue = fixture["fixture"]["venue"]


        all_fixtures.append({

            "fixture_id": fixture["fixture"]["id"],

            "league_id": league_id,
            "league": league_name,

            "date": fixture["fixture"]["date"],

            "home_team": fixture["teams"]["home"]["name"],
            "away_team": fixture["teams"]["away"]["name"],

            "venue_id": venue["id"],
            "venue": venue["name"],
            "city": venue["city"]

        })


df = pd.DataFrame(all_fixtures)


df.to_csv(
    "england_top5_2026_fixtures.csv",
    index=False
)


print("")
print("COMPLETE")
print(f"Total fixtures: {len(df)}")
print("")
print(df.head())