import csv

with open("fixtures_clean.csv", "r", encoding="utf-8") as f:
    reader = csv.reader(f)

    header = next(reader)
    row = next(reader)

    print("Header columns:", len(header))
    print("Row columns:", len(row))

    print("\nHeader:")
    print(header)

    print("\nRow:")
    print(row)