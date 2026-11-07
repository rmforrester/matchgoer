import type { GroundReview } from "../types/grounds";

export default function PassportGroundRating({ review, busy, editing, onRate }: {
  review: GroundReview | null; busy: boolean; editing: boolean; onRate: () => void;
}) {
  const value = review?.overall_score;
  const score = typeof value === "number" && Number.isFinite(value) && value >= 1 && value <= 10 ? value : null;
  const saved = review != null && [review.overall_score, review.recommend, review.atmosphere_score,
    review.pubs_score, review.getting_there_score, review.facilities_score].some(value => value != null);
  return <div className="passport-rating-row">
    <div className="passport-rating-copy"><span className="font-bold">Ground rating</span>
      {score === null ? <span className="text-[var(--tt-muted)]">Not yet rated</span> : <span className="font-bold text-[var(--brand-interactive)]"><span aria-hidden="true" className="passport-rating-stars">{"★".repeat(Math.round(score / 2))}{"☆".repeat(5 - Math.round(score / 2))}</span> <span className="whitespace-nowrap">{score.toFixed(1)} / 10</span></span>}
    </div>
    <button type="button" disabled={busy} aria-expanded={editing} onClick={onRate} className="tt-action tt-action-secondary passport-rating-button">
      <span aria-hidden="true">{saved ? "✎" : "☆"}</span>{saved ? "Edit Rating" : "Rate Ground"}
    </button>
  </div>;
}
