import type { VenueGuide as VenueGuideData } from "../../lib/venue-guide";

type Props = { guide: VenueGuideData };

const freshnessLabel = {
  current: null,
  needs_review: "Needs review",
  expired: "Out of date",
} as const;

export default function VenueGuide({ guide }: Props) {
  if (guide.sections.length === 0) return null;
  return (
    <section className="tt-section-rule mt-10 pt-4" aria-labelledby="venue-guide-heading">
      <p className="tt-kicker">Know before you go</p>
      <h2 id="venue-guide-heading" className="tt-display mt-1 text-4xl leading-none sm:text-5xl">Plan the matchday</h2>
      <p className="mt-2 max-w-2xl text-sm text-[var(--tt-muted)]">Practical answers with their source and freshness kept visible.</p>
      <div className="mt-6 grid gap-7">
        {guide.sections.map((section) => (
          <section key={section.key} aria-labelledby={`guide-${section.key}`}>
            <h3 id={`guide-${section.key}`} className="tt-display text-3xl leading-none">{section.label}</h3>
            <div className="mt-3 border-t-2 border-[var(--tt-ink)]">
              {section.facts.map((fact) => {
                const stale = freshnessLabel[fact.freshness];
                return <article key={fact.topic} className="grid gap-2 border-b border-[var(--tt-rule)] py-4 sm:grid-cols-[11rem_minmax(0,1fr)]">
                  <h4 className="text-xs font-extrabold uppercase tracking-[0.08em]">{fact.topic}</h4>
                  <div>
                    <p className="leading-7">{fact.content}</p>
                    <p className="mt-2 text-xs font-bold text-[var(--tt-muted)]">
                      {fact.provenance.source_url ? <a href={fact.provenance.source_url} target="_blank" rel="noreferrer" className="text-[var(--tt-blue)] underline decoration-2 underline-offset-4">{fact.provenance.label}</a> : fact.provenance.label}
                      {fact.provenance.last_checked ? ` · Last checked ${new Date(`${fact.provenance.last_checked}T00:00:00`).toLocaleDateString()}` : ""}
                      {stale ? <span className="ml-2 text-amber-800">· {stale}</span> : null}
                    </p>
                  </div>
                </article>;
              })}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
