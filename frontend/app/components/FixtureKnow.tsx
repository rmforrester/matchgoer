import { hasKnowContent, selectFixtureKnowHighlights, type FixtureKnow as FixtureKnowData, type KnowFact } from "../../lib/know-v1";

function FactList({ facts }: { facts: KnowFact[] }) {
  return <div className="mt-2 divide-y divide-[var(--mg-rule)]">{facts.map((fact) => <article key={fact.know_fact_id} className="py-2 first:pt-0 last:pb-0">
    {fact.headline && <h4 className="tt-display text-[clamp(1.25rem,2.5vw,1.65rem)] font-extrabold uppercase leading-[1.1] break-words">{fact.headline}</h4>}
    <p className={`${fact.headline ? "mt-1 " : ""}max-w-3xl text-[15px] leading-6`}>{fact.content}</p>
  </article>)}</div>;
}

export default function FixtureKnow({ know, teamName }: { know: FixtureKnowData | null; teamName: string }) {
  if (!hasKnowContent(know) || !know) return null;
  const highlights = selectFixtureKnowHighlights(know);
  const matchdayFacts = [highlights.primaryMatchday, ...highlights.secondaryMatchday].filter((fact): fact is KnowFact => Boolean(fact));
  const clubFacts = [highlights.primaryIdentityModule === "CLUB" ? highlights.primaryIdentity : null, ...highlights.secondaryClub].filter((fact): fact is KnowFact => Boolean(fact));
  const supporterFacts = [highlights.primaryIdentityModule === "SUPPORTERS" ? highlights.primaryIdentity : null, ...highlights.secondarySupporters].filter((fact): fact is KnowFact => Boolean(fact));
  const hasBackground = clubFacts.length > 0 || supporterFacts.length > 0;
  const hasMatchdayGuide = hasBackground || matchdayFacts.length > 0 || know.dont_miss.length > 0 || know.good_to_know.length > 0;
  const showClubLabel = supporterFacts.length > 0 || clubFacts.length > 1 || !clubFacts[0]?.headline;
  const showSupporterLabel = clubFacts.length > 0 || supporterFacts.length > 1 || !supporterFacts[0]?.headline;

  return <>
    {hasMatchdayGuide && <section className="mg-editorial-rule mt-5 pt-3" aria-label="Matchday guide">
      <p className="mg-section-label">03 / Matchday guide</p>
      {matchdayFacts.length > 0 && <section className="mt-3 max-w-3xl" aria-labelledby="matchday-essentials-heading">
        <h3 id="matchday-essentials-heading" className="text-xs font-semibold text-[var(--tt-muted)]">Worth knowing</h3>
        <FactList facts={matchdayFacts} />
      </section>}
      {know.dont_miss.length > 0 && <section className="mg-editorial-accent mt-4 max-w-3xl bg-[var(--mg-paper-light)] px-4 py-3 sm:px-5" aria-labelledby="dont-miss-heading">
        <h3 id="dont-miss-heading" className="text-xs font-semibold text-[var(--tt-muted)]">Don&apos;t miss</h3>
        <FactList facts={know.dont_miss} />
      </section>}
      {know.good_to_know.length > 0 && <section className="mt-4 max-w-3xl" aria-labelledby="useful-to-know-heading">
        <h3 id="useful-to-know-heading" className="text-xs font-semibold text-[var(--tt-muted)]">Useful to know</h3>
        <FactList facts={know.good_to_know} />
      </section>}
    {hasBackground && <section className={matchdayFacts.length > 0 || know.dont_miss.length > 0 || know.good_to_know.length > 0 ? "mt-4 border-t border-[var(--mg-rule)] pt-3" : "mt-3"} aria-labelledby="know-heading">
      <h2 id="know-heading" className="sr-only">{teamName}</h2>
      <div className="grid gap-x-8 gap-y-4 lg:grid-cols-2">
        {clubFacts.length > 0 && <section aria-label="Club context"><h3 id="about-club-heading" className={showClubLabel ? "text-xs font-semibold text-[var(--tt-muted)]" : "sr-only"}>The club</h3><FactList facts={clubFacts} /></section>}
        {supporterFacts.length > 0 && <section aria-label="Supporter context"><h3 id="supporters-heading" className={showSupporterLabel ? "text-xs font-semibold text-[var(--tt-muted)]" : "sr-only"}>The supporters</h3><FactList facts={supporterFacts} /></section>}
      </div>
    </section>}
    </section>}

    {know.before_match.length > 0 && <section className="mg-editorial-rule mt-5 pt-3" aria-labelledby="before-kickoff-heading">
      <h2 id="before-kickoff-heading" className="mg-section-label">04 / Before the match</h2>
      <div className="mt-2 divide-y divide-[var(--mg-rule)] border-y border-[var(--mg-rule)]">{know.before_match.map((spot) => <article key={spot.pre_match_spot_id} className="grid gap-1 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div className="min-w-0">
          <h3 className="tt-display text-xl font-extrabold uppercase leading-[1.1] break-words">{spot.display_name}</h3>
          {spot.supporting_line && <p className="mt-1 max-w-2xl text-[15px] leading-6">{spot.supporting_line}</p>}
        </div>
        {spot.directions_url && <a href={spot.directions_url} target="_blank" rel="noreferrer" className="mg-tertiary-action inline-flex items-center self-end">Directions →</a>}
      </article>)}</div>
    </section>}


  </>;
}
