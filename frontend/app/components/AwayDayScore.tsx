type Props = {
  reviewCount?: number; recommendPercentage?: number | null;
  categoryScores?: { atmosphere: number | null; pubs_restaurants: number | null; getting_there: number | null; stadium_food_facilities: number | null };
};

export default function AwayDayScore({ reviewCount, recommendPercentage, categoryScores }: Props) {
  const hasReviews = (reviewCount ?? 0) > 0;
  const formatScore = (value: number | null) => value === null ? "—" : value < 5 ? "<5" : value.toFixed(1);
  const categories = [
    { label: "Atmosphere", value: categoryScores?.atmosphere ?? null },
    { label: "Pubs & restaurants", value: categoryScores?.pubs_restaurants ?? null },
    { label: "Getting there", value: categoryScores?.getting_there ?? null },
    { label: "Stadium / food / facilities", value: categoryScores?.stadium_food_facilities ?? null },
  ];
  return (
    <section className="tt-section-rule mt-10 pt-4" aria-labelledby="rating-heading">
      <p className="tt-kicker">02 / Terrace Rating</p>
      <div className="mt-1 flex flex-wrap items-end justify-between gap-4"><h2 id="rating-heading" className="tt-display text-4xl leading-none sm:text-5xl">What the terrace says</h2>{hasReviews && recommendPercentage !== undefined && recommendPercentage !== null && <p className="text-sm font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)]">{Math.round(recommendPercentage)}% would recommend</p>}</div>
      {hasReviews ? <dl className="mt-5 grid border-l-2 border-t-2 border-[var(--tt-ink)] sm:grid-cols-2">{categories.map((category) => <div key={category.label} className="flex min-h-28 items-end justify-between gap-4 border-b-2 border-r-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-4"><dt className="max-w-40 text-xs font-extrabold uppercase tracking-[0.08em]">{category.label}</dt><dd className="tt-display text-4xl leading-none" aria-label={`${category.label}: ${formatScore(category.value)}`}>{formatScore(category.value)}</dd></div>)}</dl> : <div className="mt-5 border-y-2 border-[var(--tt-ink)] py-6"><p className="tt-display text-3xl">No Terrace Rating yet.</p><p className="mt-2 text-[var(--tt-muted)]">Be the first supporter to rate this ground.</p></div>}
    </section>
  );
}
