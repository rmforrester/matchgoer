import { primaryGuideSections, secondaryGuideSections, supporterFacingFactContent, ticketPresentation, type VenueGuide as VenueGuideData, type VenueGuideFact } from "../../lib/venue-guide";

type Props = { guide: VenueGuideData };

const freshnessLabel = {
  current: null,
  needs_review: "Needs review",
  expired: "Out of date",
} as const;

export default function VenueGuide({ guide }: Props) {
  const sections = primaryGuideSections(guide);
  const secondarySections = secondaryGuideSections(guide);
  const ticket = ticketPresentation(guide);
  if (guide.sections.length === 0) return null;
  const factRow = (fact: VenueGuideFact, sectionKey: string) => {
    const stale = freshnessLabel[fact.freshness];
    const isTicketLink = sectionKey === "tickets_entry" && fact.provenance.source_url === ticket.url;
    return <article key={fact.topic} className="border-b border-[var(--tt-rule)] py-4">
      <h4 className="text-xs font-extrabold uppercase tracking-[0.08em]">{fact.topic}</h4>
      <p className="mt-2 leading-7">{supporterFacingFactContent(fact)}</p>
      {isTicketLink && <a href={fact.provenance.source_url!} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-11 items-center bg-[var(--tt-blue)] px-4 text-xs font-extrabold uppercase tracking-[0.08em] text-white">Buy tickets →</a>}
      <p className="mt-2 text-xs font-bold text-[var(--tt-muted)]">
        {fact.provenance.source_url && !isTicketLink ? <a href={fact.provenance.source_url} target="_blank" rel="noreferrer" className="text-[var(--tt-blue)] underline decoration-2 underline-offset-4">{fact.provenance.label}</a> : fact.provenance.label}
        {stale ? <span className="ml-2 text-amber-800"> · {stale}</span> : null}
      </p>
    </article>;
  };
  return (
    <section className="tt-section-rule mt-10 pt-4" aria-labelledby="venue-guide-heading">
      <p className="tt-kicker">Know before you go</p>
      <h2 id="venue-guide-heading" className="tt-display mt-1 text-4xl leading-none sm:text-5xl">The essentials</h2>
      <div className="mt-6 grid gap-7 md:grid-cols-2">
        {ticket.unknownMessage && <section aria-labelledby="guide-tickets-unknown">
          <h3 id="guide-tickets-unknown" className="tt-display text-3xl leading-none">Tickets</h3>
          <p className="mt-3 border-y-2 border-[var(--tt-ink)] py-4">{ticket.unknownMessage}</p>
        </section>}
        {sections.map((section) => (
          <section key={section.key} aria-labelledby={`guide-${section.key}`}>
            <h3 id={`guide-${section.key}`} className="tt-display text-3xl leading-none">{section.label}</h3>
            <div className="mt-3 border-t-2 border-[var(--tt-ink)]">
              {section.facts.map((fact) => factRow(fact, section.key))}
            </div>
          </section>
        ))}
      </div>
      {secondarySections.length > 0 && <details className="mt-7 border-y-2 border-[var(--tt-ink)] py-4">
        <summary className="cursor-pointer text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)]">More ground information</summary>
        <div className="mt-4 grid gap-7 md:grid-cols-2">
          {secondarySections.map((section) => <section key={section.key} aria-labelledby={`guide-more-${section.key}`}>
            <h3 id={`guide-more-${section.key}`} className="tt-display text-2xl leading-none">{section.label}</h3>
            <div className="mt-2">{section.facts.map((fact) => factRow(fact, section.key))}</div>
          </section>)}
        </div>
      </details>}
    </section>
  );
}
