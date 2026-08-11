type Venue = {
  name: string;
  city: string;
  country: string;
  capacity: number;
};

type Props = {
  venue: Venue;
  hasVisited?: boolean;
  hasCompletedReview?: boolean;
  onAddStadium?: () => void;
  onCompleteReview?: () => void;
  onEditReview?: () => void;
};

export default function VenueHeader({
  venue,
  hasVisited = false,
  hasCompletedReview = false,
  onAddStadium,
  onCompleteReview,
  onEditReview,
}: Props) {
  return (
    <div
      style={{
        marginBottom: "30px",
      }}
    >
      <h1
        style={{
          margin: "0 0 6px 0",
          fontSize: "32px",
          fontWeight: "800",
          color: "#fff",
        }}
      >
        {venue.name}
      </h1>

      <p
        style={{
          margin: "0 0 4px 0",
          color: "#fff",
        }}
      >
        {venue.city}, {venue.country}
      </p>

      <p
        style={{
          margin: "0 0 16px 0",
          color: "#fff",
        }}
      >
        Capacity: {venue.capacity.toLocaleString()}
      </p>

      {/* User stadium status */}

      {!hasVisited && (
        <button
          type="button"
          onClick={onAddStadium}
          style={{
            border: "1px solid #111827",
            borderRadius: "8px",
            padding: "9px 14px",
            background: "#111827",
            color: "#fff",
            fontWeight: "600",
            cursor: "pointer",
          }}
        >
          + Add to My Stadiums
        </button>
      )}

      {hasVisited &&
        !hasCompletedReview && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontWeight: "600",
                color: "#fff",
              }}
            >
              ✓ You've visited this stadium
            </span>

            <button
              type="button"
              onClick={onCompleteReview}
              style={{
                border: "1px solid #111827",
                borderRadius: "8px",
                padding: "8px 13px",
                background: "#fff",
                color: "#111827",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Complete your review →
            </button>
          </div>
        )}

      {hasVisited &&
        hasCompletedReview && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontWeight: "600",
                color: "#fff",
              }}
            >
              ✓ You've visited this stadium
            </span>

            <button
              type="button"
              onClick={onEditReview}
              style={{
                border: "1px solid #111827",
                borderRadius: "8px",
                padding: "8px 13px",
                background: "#fff",
                color: "#111827",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Edit your review
            </button>
          </div>
        )}
    </div>
  );
}