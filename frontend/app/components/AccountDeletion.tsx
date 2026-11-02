"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthProvider";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { appleDeletionCode } from "@/lib/apple-signin";
import api, { anonymousApi } from "@/lib/api";

type RequestState = { request_type?: "account" | "guest_history"; manual_review_required?: boolean; request_id: string; status: "pending" | "processing" | "completed"; due_at: string; completed_at?: string; apple_revocation?: string };

function requestState(value: unknown): RequestState | null {
  if (value === null) return null;
  const row = value as Partial<RequestState> | undefined;
  if (!row || typeof row.request_id !== "string" || !row.request_id ||
      !["pending", "processing", "completed"].includes(row.status ?? "") ||
      typeof row.due_at !== "string" || !Number.isFinite(Date.parse(row.due_at)) ||
      (row.status === "completed" && (!row.completed_at || !Number.isFinite(Date.parse(row.completed_at))))) {
    throw new Error("Deletion status was not confirmed");
  }
  return row as RequestState;
}

export default function AccountDeletion({ guest = false }: { guest?: boolean }) {
  const { accountKey } = useAuth();
  const scope = useRef<AbortController | null>(null);
  const transport = guest ? anonymousApi : api;
  const [request, setRequest] = useState<RequestState | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const controller = new AbortController(); scope.current = controller;
    void transport.get("/account/deletion-request", { signal: controller.signal }).then(result => {
      if (active) setRequest(requestState(result.data));
    }).catch(() => {
      if (active) setError("We couldn't check your deletion request. Retry before sending another request.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [transport]);
  async function ownerOptions() {
    const controller = scope.current;
    if (!controller || controller.signal.aborted) throw new Error("Account changed");
    const result = await getSupabaseBrowserClient()?.auth.getSession();
    if (result?.error) throw result.error;
    const session = result?.data.session;
    if ((guest && session) || (!guest && (!session || session.user.id !== accountKey)) || controller.signal.aborted) throw new Error("Account changed");
    return { signal: controller.signal, headers: session ? { Authorization: `Bearer ${session.access_token}` } : undefined };
  }
  async function send(code?: string) {
    const options = await ownerOptions();
    const result = await transport.post("/account/deletion-request", { confirmed: true, ...(guest ? { guest_history: true } : {}), ...(code ? { apple_authorization_code: code } : {}) }, options);
    if (options.signal.aborted) throw new Error("Account changed");
    const acknowledged = requestState(result.data);
    if (!acknowledged) throw new Error("Request not acknowledged");
    setRequest(acknowledged);
    if (result.data.receipt) {
      try { localStorage.setItem("matchgoer.deletion-receipt.v1", result.data.receipt); }
      catch { setError("Your request is recorded, but this browser could not retain its completion receipt. Keep the reference and return here before deletion is completed."); }
    }
    return acknowledged;
  }
  async function submit() {
    if (!confirmed || busy || loading || error) return;
    setBusy(true);
    try { const acknowledged = await send(); await finishApple(acknowledged); }
    catch { if (!scope.current?.signal.aborted) setError("We couldn't confirm your request. Check its status before trying again."); }
    finally { setBusy(false); }
  }
  async function finishApple(current = request, force = false) {
    if (guest || !current || current.apple_revocation === "not_required" || (!force && current.apple_revocation !== "pending")) return;
    try {
      await ownerOptions();
      const result = await getSupabaseBrowserClient()?.auth.getUser();
      if (result?.error || result?.data.user?.id !== accountKey) throw new Error("Account changed");
      let code: string | undefined;
      if (result.data.user.identities?.some(item => item.provider === "apple")) code = await appleDeletionCode();
      await send(code); // Rechecks the original identity after Apple's system UI.
    } catch {
      if (!scope.current?.signal.aborted) setError("Your deletion request is recorded. Apple authorization was not completed. You can retry it below.");
    }
  }
  async function saveReceipt() {
    if (busy) return;
    setBusy(true);
    try { await send(); setError(""); }
    catch { if (!scope.current?.signal.aborted) setError("Couldn't save a completion receipt. Please retry while you are still signed in to this history."); }
    finally { setBusy(false); }
  }
  async function retry() {
    setBusy(true);
    try { const result = await transport.get("/account/deletion-request", { signal: scope.current?.signal }); if (!scope.current?.signal.aborted) { setRequest(requestState(result.data)); setError(""); } }
    catch { if (!scope.current?.signal.aborted) setError("We couldn't check your request. Please try again."); }
    finally { setBusy(false); }
  }
  return <details className="mt-3 border-t border-[var(--tt-rule)] pt-2">
    <summary className="min-h-11 cursor-pointer content-center font-bold underline focus-visible:outline-2">{guest ? "Delete guest history" : "Delete account"}</summary>
    {guest && <p className="mt-3 text-sm">This request covers the guest history recorded now. Signing in does not request deletion of unrelated account history. Transferred or changed records require protected scope review.</p>}
    {loading ? <p role="status">Checking your request...</p> : request ? <div role="status" className="mt-3 text-sm">
      <p className="font-bold">{request.status === "completed" ? "Account deletion completed" : "Account deletion requested"}</p>
      <p>{request.status === "completed" ? "A completion confirmation is sent separately." : `We will complete your request within seven calendar days, by ${new Date(request.due_at).toLocaleDateString()}. No email or support request is needed.`}</p>
      {request.apple_revocation === "pending" && <p className="mt-2">Your request is recorded. Apple access checks may still require follow-up before completion.</p>}
      {!guest && request.status !== "completed" && ["pending", "complete"].includes(request.apple_revocation ?? "") && <button type="button" disabled={busy} onClick={() => void finishApple(request, true)} className="min-h-11 font-bold underline">Verify Apple access</button>}
      {request.status !== "completed" && <button type="button" disabled={busy} onClick={() => void saveReceipt()} className="block min-h-11 font-bold underline">Save completion receipt in this browser</button>}
      <p className="mt-2 break-all">Reference: {request.request_id}</p>
    </div> : <div className="mt-3 grid gap-3 text-sm">
      <p>{guest ? "Request permanent deletion of the guest history owned by this browser." : "Request permanent deletion of your account, saved matchdays, attendance, reviews and uploaded photographs."} We will complete the request within seven calendar days and provide a completion receipt here and send confirmation to your account email where available. Your history remains available until deletion is completed.</p>
      <p>Limited records may be retained where legally required. Isolated backups expire under the backup retention policy and will not be used to restore your account.</p>
      <label className="flex items-start gap-3"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} className="mt-1 h-5 w-5 shrink-0" />I understand that completed deletion is permanent and want to request it.</label>
      <button type="button" disabled={!confirmed || busy || !!error} onClick={() => void submit()} className="tt-action min-h-11 px-4">{busy ? "Sending request..." : "Confirm deletion request"}</button>
    </div>}
    {error && <div role="alert" className="mt-3 text-sm"><p>{error}</p><button type="button" disabled={busy} onClick={() => void retry()} className="min-h-11 font-bold underline">Check request status</button></div>}
  </details>;
}

export function DeletionRequestQueue() {
  const [rows, setRows] = useState<(RequestState & { user_id: number })[] | null>(null);
  const [error, setError] = useState("");
  async function load() {
    setError("");
    try { const result = await api.get("/account/moderator/deletion-requests"); setRows(result.data); }
    catch { setError("Unable to load the protected queue. Check your moderator sign-in and retry."); }
  }
  return <details className="mt-3"><summary className="min-h-11 cursor-pointer content-center font-bold">Account deletion requests</summary>
    <button type="button" onClick={() => void load()} className="min-h-11 font-bold underline">Refresh pending requests</button>
    {error && <p role="alert">{error}</p>}
    {rows && <><p role="status">{rows.length} pending request(s)</p><ul className="grid gap-3">{rows.map(row => <li key={row.request_id} className="break-all border-t border-[var(--tt-rule)] pt-2 text-sm">{row.request_type === "guest_history" ? "Guest history" : row.request_type === "account" ? "Account" : "Unverified scope"} {row.user_id} &middot; {row.status} &middot; Apple access: {row.apple_revocation ?? "not checked"}{(row.manual_review_required || !row.request_type) && <p className="font-bold">Protected manual scope review required. Do not delete authenticated-account history.</p>}<br />Due {new Date(row.due_at).toLocaleString()}<br />Reference {row.request_id}</li>)}</ul></>}
  </details>;
}

export function BlockedMatchgoers() {
  const [rows, setRows] = useState<{ block_id: number; display_name: string }[] | null>(null);
  const [error, setError] = useState("");
  async function load() {
    try { const result = await api.get("/account/blocked-matchgoers"); setRows(result.data); setError(""); }
    catch { setError("Couldn't load blocked matchgoers. Please try again."); }
  }
  async function unblock(blockId: number) {
    try { await api.delete(`/account/blocked-matchgoers/${blockId}`); await load(); }
    catch { setError("Couldn't confirm this change. Refresh and try again."); }
  }
  return <details className="mt-3"><summary className="min-h-11 cursor-pointer content-center font-bold">Blocked matchgoers</summary><p className="text-sm">Their photographs and authored tips are hidden while you are signed in. Blocking does not report content to moderators.</p>
    <button type="button" className="min-h-11 font-bold underline" onClick={() => void load()}>Refresh blocked matchgoers</button>
    {error && <p role="alert">{error}</p>}{rows?.length === 0 && <p>No blocked matchgoers.</p>}
    {rows?.map(row => <div key={row.block_id} className="flex flex-wrap items-center justify-between gap-2"><span>{row.display_name}</span><button type="button" className="min-h-11 font-bold underline" onClick={() => void unblock(row.block_id)}>Unblock</button></div>)}
  </details>;
}

export function GuestDeletionAndReceipt() {
  const { authenticated, loading, accountKey } = useAuth();
  const [show, setShow] = useState(false);
  const providerOwner = accountKey !== "guest";
  const [message, setMessage] = useState("");
  async function check() {
    try {
      const receipt = localStorage.getItem("matchgoer.deletion-receipt.v1");
      if (!receipt) { setMessage("No deletion receipt is stored in this browser."); return; }
      const result = await anonymousApi.post("/account/deletion-receipt", { receipt });
      const state = requestState(result.data);
      if (!state) throw new Error("Receipt not confirmed");
      setMessage(state.status === "completed" ? `Deletion completed for receipt ${state.request_id}.` : `Receipt ${state.request_id}: request is ${state.status}. Due ${new Date(state.due_at).toLocaleDateString()}.`);
    } catch { setMessage("Couldn't check the completion receipt. Please retry."); }
  }
  return <section className="mt-5 border-t border-[var(--tt-rule)] pt-4"><h2 className="font-extrabold">Deletion requests and receipts</h2><p className="text-sm">Guest history belongs to this browser. This checks the most recent deletion receipt saved here; match its reference to your acknowledgement. Keep this browser data until completion; clearing it removes your receipt. Completed receipts can be checked for 90 days.</p>{!authenticated && !loading && <button type="button" onClick={() => setShow(value => !value)} className="min-h-11 font-bold underline">{show ? "Close deletion request" : providerOwner ? "Delete account" : "Delete guest history"}</button>}{!authenticated && !loading && show && <AccountDeletion key={accountKey} guest={!providerOwner} />}<button type="button" onClick={() => void check()} className="block min-h-11 font-bold underline">Check deletion completion receipt</button>{message && <p role="status">{message}</p>}</section>;
}
