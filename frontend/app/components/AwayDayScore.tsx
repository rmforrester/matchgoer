type Props = {
  score?: number;
  reviewCount?: number;
  recommendPercentage?: number | null;
  categoryScores?: {
    atmosphere: number | null;
    pubs_restaurants: number | null;
    getting_there: number | null;
    stadium_food_facilities: number | null;
  };
  myScore?: number | null;
};

export default function AwayDayScore({
  score,
  reviewCount,
  recommendPercentage,
  categoryScores,
  myScore,
}: Props) {
  const hasReviews =
    (reviewCount ?? 0) > 0;

  const formatCategoryScore = (
    value: number | null
  ) => {
    if (value === null) {
      return "--";
    }

    if (value < 5) {
      return "<5";
    }

    return value.toFixed(1);
  };

  const categories = [
  {
    label: "Atmosphere",
    emoji: "🥁",
    value:
      categoryScores?.atmosphere ?? null,
  },
  {
    label: "Pubs & Restaurants",
    emoji: "🍺",
    value:
      categoryScores?.pubs_restaurants ??
      null,
  },
  {
    label: "Getting There",
    emoji: "🚆",
    value:
      categoryScores?.getting_there ??
      null,
  },
  {
    label: "Stadium / Food / Facilities",
    emoji: "🏟️",
    value:
      categoryScores?.stadium_food_facilities ??
      null,
  },
];

  return (
    <div
      style={{
        border: "1px solid #ddd",
        borderRadius: "12px",
        padding: "24px",
        marginBottom: "24px",
        background: "#fff",
      }}
    >
      <div
        style={{
          fontSize: "20px",
          fontWeight: "700",
          marginBottom: "20px",
          color: "#111827",
        }}
      >
        🎟️ Terrace Rating
      </div>

      {hasReviews ? (
        <>
          {/* ---------------------------------------------
              TWO PRIMARY RATINGS
          --------------------------------------------- */}

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(2, minmax(0, 1fr))",
              gap: "16px",
              marginBottom: "24px",
            }}
          >

            {/* Terrace Rating */}

            <div
              style={{
                border: "1px solid #eee",
                borderRadius: "10px",
                padding: "18px",
              }}
            >
              <div
                style={{
                  fontSize: "14px",
                  fontWeight: "600",
                  color: "#555",
                  marginBottom: "8px",
                }}
              >
                🎟️ Terrace Rating
              </div>

              <div
                style={{
                  fontSize: "42px",
                  lineHeight: "1",
                  fontWeight: "800",
                  color: "#111827",
                }}
              >
                {score !== undefined &&
                score !== null
                  ? score.toFixed(1)
                  : "--"}
              </div>

              <div
                style={{
                  marginTop: "6px",
                  fontSize: "13px",
                  color: "#777",
                }}
              >
                out of 10
              </div>
            </div>


            {/* Away Day Rating */}

            <div
              style={{
                border: "1px solid #eee",
                borderRadius: "10px",
                padding: "18px",
              }}
            >
              <div
                style={{
                  fontSize: "14px",
                  fontWeight: "600",
                  color: "#555",
                  marginBottom: "8px",
                }}
              >
                👍 Away Day Rating
              </div>

              <div
                style={{
                  fontSize: "42px",
                  lineHeight: "1",
                  fontWeight: "800",
                  color: "#111827",
                }}
              >
                {recommendPercentage !==
                undefined &&
                recommendPercentage !== null
                  ? `${Math.round(
                      recommendPercentage
                    )}%`
                  : "--"}
              </div>

              <div
                style={{
                  marginTop: "6px",
                  fontSize: "13px",
                  color: "#777",
                }}
              >
                would recommend
              </div>
            </div>

          </div>


          {/* Review count */}

          <p
            style={{
              margin: "0 0 24px 0",
              color: "#555",
            }}
          >
            Based on {reviewCount ?? 0} supporter{" "}
            {reviewCount === 1
              ? "review"
              : "reviews"}
          </p>
{myScore !== undefined &&
  myScore !== null && (
    <p
      style={{
        margin: "0 0 24px 0",
        fontSize: "15px",
        fontWeight: "600",
        color: "#111827",
      }}
    >
      Your Terrace Rating:{" "}
      <span
        style={{
          fontSize: "18px",
          fontWeight: "800",
        }}
      >
        {myScore.toFixed(1)}
      </span>
    </p>
  )}

          {/* ---------------------------------------------
              CATEGORY BREAKDOWN
          --------------------------------------------- */}

          <div
            style={{
              borderTop: "1px solid #eee",
              paddingTop: "20px",
            }}
          >
            <h3
              style={{
                margin: "0 0 16px 0",
                fontSize: "17px",
                color: "#111827",
              }}
            >
              Rating Breakdown
            </h3>

            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(2, minmax(0, 1fr))",
                gap: "12px",
              }}
            >
              {categories.map(
                (category) => (
                  <div
                    key={category.label}
                    style={{
                      border: "1px solid #eee",
                      borderRadius: "10px",
                      padding: "14px",
                    }}
                  >
<div
  style={{
    fontSize: "14px",
    color: "#555",
    marginBottom: "6px",
  }}
>
  <span
    style={{
      marginRight: "6px",
    }}
  >
    {category.emoji}
  </span>

  {category.label}
</div>

                    <div
                      style={{
                        fontSize: "24px",
                        fontWeight: "700",
                        color: "#111827",
                      }}
                    >
                      {formatCategoryScore(
                        category.value
                      )}
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          <h1
            style={{
              fontSize: "52px",
              lineHeight: "1",
              margin: "12px 0",
              fontWeight: "800",
              color: "#777",
            }}
          >
            --
          </h1>

          <p
            style={{
              margin: 0,
              color: "#777",
            }}
          >
            Not enough supporter reviews yet.
          </p>
        </>
      )}
    </div>
  );
}