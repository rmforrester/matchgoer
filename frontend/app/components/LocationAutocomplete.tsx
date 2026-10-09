"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AUTOCOMPLETE_DELAY, autocompleteParameters, locationSuggestions, type LocationSuggestion } from "../../lib/location-autocomplete";

type Props = { value: string; onChange: (value: string) => void; onSelect: (location: LocationSuggestion) => void; disabled?: boolean };
type State = { query: string; items: LocationSuggestion[]; status: "loading" | "ready" | "error" };

export default function LocationAutocomplete({ value, onChange, onSelect, disabled = false }: Props) {
  const listId = useId();
  const key = process.env.NEXT_PUBLIC_GEOAPIFY_API_KEY;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [state, setState] = useState<State | null>(null);
  const version = useRef(0);
  const request = useRef<AbortController | null>(null);
  const container = useRef<HTMLDivElement | null>(null);
  const cache = useRef(new Map<string, { at: number; items: LocationSuggestion[] }>());
  const query = value.trim();
  const invalidate = () => { version.current += 1; request.current?.abort(); };
  const dismiss = () => { invalidate(); setOpen(false); setActive(-1); };
  const select = (item: LocationSuggestion) => { dismiss(); setState(null); onSelect(item); };

  useEffect(() => {
    // Close after an outside click has reached its target. Closing on pointer
    // blur would move the form before the user's click can reach a control.
    const outsideClick = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) {
        version.current += 1;
        request.current?.abort();
        setOpen(false);
        setActive(-1);
      }
    };
    document.addEventListener("click", outsideClick);
    return () => document.removeEventListener("click", outsideClick);
  }, []);

  useEffect(() => {
    if (open && active >= 0) document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active, open, listId]);

  useEffect(() => {
    const params = autocompleteParameters(query);
    if (!open || disabled || !params) return;
    const generation = ++version.current;
    const controller = new AbortController();
    request.current = controller;
    const timer = setTimeout(async () => {
      if (!key) { setState({ query, items: [], status: "error" }); return; }
      const cached = cache.current.get(query.toLowerCase());
      if (cached && Date.now() - cached.at < 300_000) {
        setState({ query, items: cached.items, status: "ready" });
        return;
      }
      setState({ query, items: [], status: "loading" });
      params.set("apiKey", key);
      const timeout = setTimeout(() => controller.abort(), 10_000);
      try {
        const response = await fetch(`https://api.geoapify.com/v1/geocode/autocomplete?${params}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Location suggestions unavailable");
        const items = locationSuggestions(await response.json());
        if (generation !== version.current) return;
        if (cache.current.size >= 40) cache.current.delete(cache.current.keys().next().value!);
        cache.current.set(query.toLowerCase(), { at: Date.now(), items });
        setState({ query, items, status: "ready" });
      } catch {
        // Never log provider URLs or key-bearing request errors.
        if (generation === version.current) setState({ query, items: [], status: "error" });
      } finally { clearTimeout(timeout); }
    }, AUTOCOMPLETE_DELAY);
    return () => { clearTimeout(timer); controller.abort(); version.current += 1; };
  }, [query, open, disabled, key]);

  const visible = open && !disabled && query.length >= 2;
  const current = state?.query === query ? state : null;
  const items = visible ? current?.items ?? [] : [];
  return <div ref={container} className="min-w-0 normal-case tracking-normal">
    <input id="location-search" type="search" role="combobox" value={value} disabled={disabled}
      autoComplete="off" aria-label="Where" aria-autocomplete="list" aria-expanded={visible}
      aria-controls={visible ? listId : undefined} aria-activedescendant={active >= 0 && items[active] ? `${listId}-${active}` : undefined}
      placeholder="Search a city or location" className="tt-control w-full min-w-0 px-4 py-2"
      onChange={(event) => { invalidate(); setState(null); setActive(-1); setOpen(true); onChange(event.target.value); }}
      onKeyDown={(event) => {
        if (event.key === "Tab") dismiss();
        if (event.key === "Escape" && visible) { event.preventDefault(); dismiss(); }
        if ((event.key === "ArrowDown" || event.key === "ArrowUp") && items.length) {
          event.preventDefault(); setActive(index => event.key === "ArrowDown" ? (index + 1) % items.length : (index <= 0 ? items.length - 1 : index - 1));
        }
        if (event.key === "Enter" && active >= 0 && items[active]) { event.preventDefault(); select(items[active]); }
      }} />
    {visible && <div className="mt-1 max-h-80 overflow-y-auto border border-[var(--brand-interactive)] bg-[var(--tt-paper)]">
      <ul id={listId} role="listbox" aria-label="Location suggestions">
        {items.map((item, index) => <li id={`${listId}-${index}`} key={item.id} role="option" aria-selected={active === index}
          onPointerDown={(event) => event.preventDefault()} onClick={() => select(item)}
          className={`min-h-14 cursor-pointer break-words border-b border-[var(--tt-rule)] px-4 py-3 last:border-b-0 ${active === index ? "bg-[var(--brand-interactive)] text-white" : "hover:bg-[var(--brand-primary-subtle)]"}`}>
          <span className="block text-sm font-bold">{item.name}</span><span className="block text-xs font-normal">{item.detail}</span>
        </li>)}
      </ul>
      <p role="status" className="break-words px-4 py-2 text-xs font-normal">
        {!current || current.status === "loading" ? "Finding locations…" : current.status === "error" ? "Location suggestions unavailable. You can still search manually." : !items.length ? "No matching locations found." : "Use arrows and Enter, or tap a location."}
      </p>
      <p className="px-4 pb-2 text-[0.65rem] font-normal">Locations by <a href="https://www.geoapify.com/" target="_blank" rel="noreferrer" className="underline">Geoapify</a> / <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="underline">OpenStreetMap</a></p>
    </div>}
  </div>;
}
