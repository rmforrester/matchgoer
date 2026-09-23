import { hasKnowContent, selectFixtureKnowHighlights, showPrimaryIdentityHeadline, type FixtureKnow as FixtureKnowData, type KnowFact } from "../../lib/know-v1";

function FactList({ facts, compact = false, showHeadlines = true }: { facts: KnowFact[]; compact?: boolean; showHeadlines?: boolean }) {
  return <div className={compact ? "mt-3 divide-y divide-[var(--tt-rule)] border-y border-[var(--tt-rule)]" : "mt-3 space-y-4"}>{facts.map((fact) => <article key={fact.know_fact_id} className={compact ? "py-3" : undefined}>
    {showHeadlines && fact.headline && <h4 className="text-sm font-extrabold uppercase tracking-[0.06em]">{fact.headline}</h4>}
    <p className={showHeadlines && fact.headline ? "mt-1 text-[0.95rem] leading-6 sm:text-base sm:leading-7" : "text-[0.95rem] leading-6 sm:text-base sm:leading-7"}>{fact.content}</p>
  </article>)}</div>;
}

export default function FixtureKnow({ know, compactTop = false }: { know: FixtureKnowData | null; compactTop?: boolean }) {
  if (!hasKnowContent(know) || !know) return null;
  const highlights = selectFixtureKnowHighlights(know);
  const hasSecondary = Boolean(highlights.secondaryMatchday.length || know.good_to_know.length || highlights.secondaryClub.length || highlights.secondarySupporters.length);
  return <section className={`tt-section-rule ${compactTop ? "mt-8" : "mt-10"} pt-4`} aria-labelledby="matchday-guide-heading">
    <p className="tt-kicker">Plan your matchday</p><h2 id="matchday-guide-heading" className="tt-display mt-1 text-4xl leading-none sm:text-5xl">Matchday guide</h2>
    {highlights.primaryIdentity && <section className="mt-6 max-w-3xl border-l-[6px] border-[var(--tt-gold)] pl-4" aria-labelledby="identity-heading">
      <p className="tt-kicker">Club &amp; supporters</p><h3 id="identity-heading" className="tt-display mt-1 text-3xl leading-none">Who you&apos;re watching</h3><FactList facts={[highlights.primaryIdentity]} showHeadlines={showPrimaryIdentityHeadline(know)} />
    </section>}
    {highlights.primaryMatchday && <section className="mt-8 max-w-3xl" aria-labelledby="matchday-essentials-heading"><h3 id="matchday-essentials-heading" className="tt-display text-3xl leading-none">Matchday essentials</h3><FactList facts={[highlights.primaryMatchday]} compact /></section>}
    {know.before_match.length > 0 && <section className="mt-8" aria-labelledby="before-kickoff-heading">
      <h3 id="before-kickoff-heading" className="tt-display text-3xl leading-none">Before the match</h3><p className="mt-2 text-sm text-[var(--tt-muted)]">Places supporters go before kickoff.</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{know.before_match.map((spot) => <article key={spot.pre_match_spot_id} className="tt-panel p-4"><h4 className="tt-display text-2xl leading-none">{spot.display_name}</h4>{spot.supporting_line && <p className="mt-2 leading-6">{spot.supporting_line}</p>}{spot.location_context && <p className="mt-2 text-sm font-bold text-[var(--tt-muted)]">{spot.location_context}</p>}{spot.directions_url && <a href={spot.directions_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-11 items-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">Directions →</a>}</article>)}</div>
    </section>}
    {know.dont_miss.length > 0 && <section className="mt-8 max-w-3xl border-l-[6px] border-[var(--tt-gold)] pl-4" aria-labelledby="dont-miss-heading"><h3 id="dont-miss-heading" className="tt-display text-3xl leading-none">Don&apos;t miss</h3><FactList facts={know.dont_miss}/></section>}
    {hasSecondary && <details className="mt-8 max-w-3xl border-y-2 border-[var(--tt-ink)] py-4">
      <summary className="min-h-11 cursor-pointer content-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">More about this matchday</summary>
      <div className="mt-4 grid gap-7 sm:grid-cols-2">
        {highlights.secondaryMatchday.length > 0 && <section aria-labelledby="more-essentials-heading"><h3 id="more-essentials-heading" className="tt-display text-2xl leading-none">More matchday essentials</h3><FactList facts={highlights.secondaryMatchday}/></section>}
        {know.good_to_know.length > 0 && <section aria-labelledby="useful-to-know-heading"><h3 id="useful-to-know-heading" className="tt-display text-2xl leading-none">Useful to know</h3><FactList facts={know.good_to_know}/></section>}
        {highlights.secondaryClub.length > 0 && <section aria-labelledby="about-club-heading"><h3 id="about-club-heading" className="tt-display text-2xl leading-none">About the club</h3><FactList facts={highlights.secondaryClub}/></section>}
        {highlights.secondarySupporters.length > 0 && <section aria-labelledby="supporters-heading"><h3 id="supporters-heading" className="tt-display text-2xl leading-none">The supporters</h3><FactList facts={highlights.secondarySupporters}/></section>}
      </div>
    </details>}
  </section>;
}
