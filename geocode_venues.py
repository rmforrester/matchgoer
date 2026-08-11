import pandas as pd
import html
import time
from geopy.geocoders import Nominatim

# Load CSV
df = pd.read_csv("venues_with_coordinates.csv")

geolocator = Nominatim(user_agent="football_finder")

def clean(text):
    if pd.isna(text):
        return ""

    text = html.unescape(str(text))

    text = text.replace("&apos;", "'")

    while "  " in text:
        text = text.replace("  ", " ")

    return text.strip()


for idx, row in df[df["latitude"].isna()].iterrows():

    name = clean(row["name"])
    address = clean(row["address"])
    city = clean(row["city"])
    country = clean(row["country"])

    # Remove county from city as an alternative
    short_city = city.split(",")[0].strip()

    searches = [
        f"{name}, {address}, {city}, {country}",
        f"{address}, {city}, {country}",
        f"{name}, {city}, {country}",
        f"{name}, {short_city}, {country}",
        f"{address}, {short_city}, {country}",
        f"{name}, {country}",
        name
    ]

    found = False

    for query in searches:

        try:
            location = geolocator.geocode(query, timeout=10)

            if location:

                df.at[idx, "latitude"] = location.latitude
                df.at[idx, "longitude"] = location.longitude

                print(f"✓ {name}")

                found = True
                break

        except Exception:
            pass

        time.sleep(1)

    if not found:
        print(f"✗ {name}")

df.to_csv("venues_with_coordinates_retry.csv", index=False)

print("Finished.")