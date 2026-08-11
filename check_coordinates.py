import pandas as pd

df = pd.read_csv("venues_with_coordinates.csv")

missing = df[df["latitude"].isna() | df["longitude"].isna()]

print(f"{len(missing)} venues missing coordinates")

missing.to_csv("missing_coords.csv", index=False)