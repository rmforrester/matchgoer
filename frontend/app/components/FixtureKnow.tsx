import { fixtureKnowDescriptor, hasKnowContent, selectFixtureKnowHighlights, type FixtureKnow as FixtureKnowData, type KnowFact } from "../../lib/know-v1";

function FactList({ facts, editorialHeadlines = false, showHeadlines = true }: { facts: KnowFact[]; editorialHeadlines?: boolean; showHeadlines?: boolean }) {
  return <div className="mt-3 divide-y divide-[var(--mg-rule)]">{facts.map((fact) => <article key={fact.know_fact_id} className="py-3 first:pt-0 last:pb-0">
    {showHeadlines && fact.headline && <h4 className={editorialHeadlines ? "mg-fact-headline" : "text-base font-extrabold leading-6"}>{fact.headline}</h4>}
    <p className={`${showHeadlines && fact.headline ? "mt-1 " : ""}mg-body max-w-3xl`}>{fact.content}</p>
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
  const backgroundDescriptor = fixtureKnowDescriptor(clubFacts.length > 0, supporterFacts.length > 0);

  return <>
    {hasMatchdayGuide && <section className="mg-editorial-rule mt-6 pt-3" aria-label="Matchday guide">
      <p className="mg-section-label">03 / Matchday guide</p>
      {matchdayFacts.length > 0 && <section className="mt-3 max-w-3xl" aria-labelledby="matchday-essentials-heading">
        <h3 id="matchday-essentials-heading" className="mg-display-callout">Worth knowing</h3>
        <FactList facts={matchdayFacts} />
      </section>}
      {know.dont_miss.length > 0 && <section className="mg-editorial-accent mt-6 max-w-3xl bg-[var(--mg-paper-light)] px-4 py-4 sm:px-5" aria-labelledby="dont-miss-heading">
        <h3 id="dont-miss-heading" className="mg-display-callout">Don&apos;t miss</h3>
        <FactList facts={know.dont_miss} />
      </section>}
      {know.good_to_know.length > 0 && <section className="mt-4 max-w-3xl" aria-labelledby="useful-to-know-heading">
        <h3 id="useful-to-know-heading" className="mg-display-callout">Useful to know</h3>
        <FactList facts={know.good_to_know} />
      </section>}
    {hasBackground && <section className="mt-4 border-t border-[var(--mg-rule)] pt-3" aria-labelledby="know-heading">
      <h2 id="know-heading" className="sr-only">{teamName}</h2>
      {backgroundDescriptor && <p className="mg-meta mt-2 font-extrabold uppercase tracking-[0.08em]">{backgroundDescriptor}</p>}
      <div className="mt-3 grid gap-x-8 gap-y-4 lg:grid-cols-2">
        {clubFacts.length > 0 && <section aria-labelledby="about-club-heading"><h3 id="about-club-heading" className="mg-section-label">The club</h3><FactList facts={clubFacts} editorialHeadlines /></section>}
        {supporterFacts.length > 0 && <section aria-labelledby="supporters-heading"><h3 id="supporters-heading" className="mg-section-label">The supporters</h3><FactList facts={supporterFacts} editorialHeadlines /></section>}
      </div>
    </section>}
    </section>}

    {know.before_match.length > 0 && <section className="mg-editorial-rule mt-6 pt-3" aria-labelledby="before-kickoff-heading">
      <h2 id="before-kickoff-heading" className="mg-section-label">04 / Before the match</h2>
      <p className="mg-meta mt-2">Places supporters go before kick-off.</p>
      <div className="mt-3 divide-y divide-[var(--mg-rule)] border-y border-[var(--mg-rule)]">{know.before_match.map((spot) => <article key={spot.pre_match_spot_id} className="grid gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div className="min-w-0">
          <h3 className="text-base font-extrabold leading-6 break-words">{spot.display_name}</h3>
          {spot.supporting_line && <p className="mg-body mt-1.5 max-w-2xl">{spot.supporting_line}</p>}
        </div>
        {spot.directions_url && <a href={spot.directions_url} target="_blank" rel="noreferrer" className="mg-tertiary-action self-end">Directions →</a>}
      </article>)}</div>
    </section>}


  </>;
}
