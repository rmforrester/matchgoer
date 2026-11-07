export default function HistoryActionIcon({ action }: { action: "change" | "matchday" | "ground" }) {
  return <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" className="shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {action === "change" ? <><path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14z"/><path d="m4 14 5 5"/></> : action === "matchday" ? <><path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/></> : <><path d="M3 7v14h18V7M3 12l9-4 9 4M3 17l9 4 9-4M12 8v13M6 4v7M18 4v7"/><path d="M10 16h4"/></>}
  </svg>;
}
