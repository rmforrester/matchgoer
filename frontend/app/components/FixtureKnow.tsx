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
  const hasMatchdayGuide = matchdayFacts.length > 0 || know.dont_miss.length > 0 || know.good_to_know.length > 0;
  const hasBackground = clubFacts.length > 0 || supporterFacts.length > 0;
  const backgroundDescriptor = fixtureKnowDescriptor(clubFacts.length > 0, supporterFacts.length > 0);

  return <>
    {hasMatchdayGuide && <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="matchday-guide-heading">
      <p className="mg-section-label">03 / Matchday guide</p>
      <h2 id="matchday-guide-heading" className="mg-display-section mt-2">Matchday guide</h2>
      {matchdayFacts.length > 0 && <section className="mt-5 max-w-3xl" aria-labelledby="matchday-essentials-heading">
        <h3 id="matchday-essentials-heading" className="mg-display-callout">Worth knowing</h3>
        <FactList facts={matchdayFacts} />
      </section>}
      {know.dont_miss.length > 0 && <section className="mg-editorial-accent mt-6 max-w-3xl bg-[var(--mg-paper-light)] px-4 py-4 sm:px-5" aria-labelledby="dont-miss-heading">
        <h3 id="dont-miss-heading" className="mg-display-callout">Don&apos;t miss</h3>
        <FactList facts={know.dont_miss} />
      </section>}
      {know.good_to_know.length > 0 && <section className="mt-6 max-w-3xl" aria-labelledby="useful-to-know-heading">
        <h3 id="useful-to-know-heading" className="mg-display-callout">Useful to know</h3>
        <FactList facts={know.good_to_know} />
      </section>}
    </section>}

    {know.before_match.length > 0 && <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="before-kickoff-heading">
      <p className="mg-section-label">04 / Before the match</p>
      <h2 id="before-kickoff-heading" className="mg-display-section mt-2">Before the match</h2>
      <p className="mg-meta mt-2">Places supporters go before kick-off.</p>
      <div className="mt-4 divide-y divide-[var(--mg-rule)] border-y border-[var(--mg-rule)]">{know.before_match.map((spot) => <article key={spot.pre_match_spot_id} className="grid gap-1 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div className="min-w-0">
          <h3 className="mg-display-callout break-words">{spot.display_name}</h3>
          {spot.supporting_line && <p className="mg-body mt-1.5 max-w-2xl">{spot.supporting_line}</p>}
          {spot.location_context && <p className="mg-meta mt-1.5 font-bold">{spot.location_context}</p>}
        </div>
        {spot.directions_url && <a href={spot.directions_url} target="_blank" rel="noreferrer" className="mg-tertiary-action self-end">Directions →</a>}
      </article>)}</div>
    </section>}

    {hasBackground && <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="know-heading">
      <p className="mg-section-label">05 / Know</p>
      <h2 id="know-heading" className="mg-display-section mt-2 break-words">{teamName}</h2>
      {backgroundDescriptor && <p className="mg-meta mt-2 font-extrabold uppercase tracking-[0.08em]">{backgroundDescriptor}</p>}
      <div className="mt-5 grid gap-x-12 gap-y-6 lg:grid-cols-2">
        {clubFacts.length > 0 && <section aria-labelledby="about-club-heading"><h3 id="about-club-heading" className="mg-section-label">The club</h3><FactList facts={clubFacts} editorialHeadlines /></section>}
        {supporterFacts.length > 0 && <section aria-labelledby="supporters-heading"><h3 id="supporters-heading" className="mg-section-label">The supporters</h3><FactList facts={supporterFacts} editorialHeadlines /></section>}
      </div>
    </section>}
  </>;
}
