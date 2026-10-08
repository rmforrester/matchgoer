import { officialChannelLinks, type OfficialChannels } from "../../lib/official-channels";

type TicketAction = { label: string; url: string; source_label: string };
type Props = { ticketAction?: TicketAction | null; channels?: OfficialChannels | null; teamName: string };

function ActionIcon({ kind }: { kind: "ticket" | "website" | "instagram" }) {
  // The existing UI uses inline SVG; no icon dependency is needed.
  return <svg aria-hidden="true" className="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    {kind === "ticket" ? <><path d="M3 7h18v4a2 2 0 0 0 0 4v2H3v-2a2 2 0 0 0 0-4V7Z" /><path d="M15 7v2m0 3v1m0 3v1" /></> : kind === "website" ? <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></> : <><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4" /><circle cx="17.5" cy="6.5" r=".8" fill="currentColor" stroke="none" /></>}
  </svg>;
}

export default function FixtureOfficialActions({ ticketAction, channels, teamName }: Props) {
  const links = officialChannelLinks(channels);
  if (!ticketAction && links.length === 0) return null;
  const actions = [
    ...(ticketAction ? [{ label: ticketAction.label, url: ticketAction.url, kind: "ticket" as const,
      accessibleLabel: `${ticketAction.label} for ${teamName} from ${ticketAction.source_label}` }] : []),
    ...links.map(link => ({ ...link, kind: link.label === "Club website" ? "website" as const : "instagram" as const,
      accessibleLabel: `${link.label} for ${teamName}` })),
  ];
  return <nav aria-label={`${teamName} official actions`} className="mg-utility-panel mt-5 overflow-hidden sm:mt-6">
    {actions.map(action => <a key={action.kind} href={action.url} target="_blank" rel="noopener noreferrer"
      aria-label={`${action.accessibleLabel} (opens in a new tab)`}
      className={`flex min-h-12 w-full items-center gap-3 px-4 py-3 text-sm font-bold transition-colors focus-visible:-outline-offset-4 sm:px-5 ${action.kind === "ticket" ? "bg-[var(--mg-green)] text-[var(--mg-paper-light)] hover:bg-[var(--mg-green-dark)]" : "border-t border-[var(--mg-rule)] text-[var(--mg-ink)] first:border-t-0 hover:bg-[var(--mg-paper)]"}`}>
      <ActionIcon kind={action.kind} /><span>{action.label}</span>
      <svg aria-hidden="true" className="ml-auto h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M14 3h7v7m0-7L10 14M10 3H3v18h18v-7" /></svg>
    </a>)}
  </nav>;
}
