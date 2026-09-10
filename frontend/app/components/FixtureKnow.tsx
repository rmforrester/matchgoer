import { hasKnowContent, type FixtureKnow as FixtureKnowData, type KnowFact } from "../../lib/know-v1";

function FactList({ facts }: { facts: KnowFact[] }) {
  return <div className="mt-3 space-y-4">{facts.map((fact) => <article key={fact.know_fact_id}>
    {fact.headline && <h4 className="text-sm font-extrabold uppercase tracking-[0.06em]">{fact.headline}</h4>}
    <p className={fact.headline ? "mt-1 text-[0.95rem] leading-6 sm:text-base sm:leading-7" : "text-[0.95rem] leading-6 sm:text-base sm:leading-7"}>{fact.content}</p>
  </article>)}</div>;
}

export default function FixtureKnow({ know }: { know: FixtureKnowData | null }) {
  if (!hasKnowContent(know) || !know) return null;
  return <section className="tt-section-rule mt-10 pt-4" aria-labelledby="know-heading">
    <p className="tt-kicker">Know</p><h2 id="know-heading" className="tt-display mt-1 text-4xl leading-none sm:text-5xl">Know the matchday</h2>
    <div className="mt-6 grid gap-7 md:grid-cols-2">
      {know.club.length > 0 && <section aria-labelledby="know-club"><h3 id="know-club" className="tt-display text-3xl leading-none">Know the club</h3><FactList facts={know.club}/></section>}
      {know.supporters.length > 0 && <section aria-labelledby="know-supporters"><h3 id="know-supporters" className="tt-display text-3xl leading-none">The supporters</h3><FactList facts={know.supporters}/></section>}
      {know.matchday.length > 0 && <section aria-labelledby="know-matchday"><h3 id="know-matchday" className="tt-display text-3xl leading-none">The matchday</h3><FactList facts={know.matchday}/></section>}
      {know.dont_miss.length > 0 && <section className="border-l-[8px] border-[var(--tt-gold)] bg-[var(--tt-paper)] p-4" aria-labelledby="know-dont-miss"><h3 id="know-dont-miss" className="tt-display text-3xl leading-none">Don&apos;t miss</h3><FactList facts={know.dont_miss}/></section>}
    </div>
    {know.before_match.length > 0 && <section className="mt-8" aria-labelledby="know-before-match">
      <h3 id="know-before-match" className="tt-display text-3xl leading-none">Before the match</h3><p className="mt-2 text-sm text-[var(--tt-muted)]">Where home supporters gather before the game.</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{know.before_match.map((spot) => <article key={spot.pre_match_spot_id} className="tt-panel p-4"><h4 className="tt-display text-2xl leading-none">{spot.display_name}</h4>{spot.supporting_line && <p className="mt-2 leading-6">{spot.supporting_line}</p>}{spot.location_context && <p className="mt-2 text-sm font-bold text-[var(--tt-muted)]">{spot.location_context}</p>}{spot.directions_url && <a href={spot.directions_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-11 items-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Directions →</a>}</article>)}</div>
    </section>}
    {know.good_to_know.length > 0 && <section className="mt-8" aria-labelledby="know-good-to-know"><h3 id="know-good-to-know" className="tt-display text-3xl leading-none">Good to know</h3><FactList facts={know.good_to_know}/></section>}
  </section>;
}
