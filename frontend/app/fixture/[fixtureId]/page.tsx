"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import api, { apiAssetUrl } from "../../../lib/api";
import { fixtureHasFinishedForSocial, fixtureStatusGroup, fixtureStatusLabel } from "../../../lib/fixture-status";
import AccountConversionPrompt from "../../components/AccountConversionPrompt";
import FixtureTeams from "../../components/FixtureTeams";
import { accountRoute } from "@/lib/auth-flow";
import { hasPendingAuthAction, parsePendingWhosGoingAction, pendingWhosGoingReturnTo } from "@/lib/pending-auth-action";
import { applyPendingWhosGoing, clearPendingWhosGoing, loadPendingWhosGoing } from "@/lib/account-conversion-checkpoint";
import FixtureKnow from "../../components/FixtureKnow";
import { type FixtureKnow as FixtureKnowData } from "../../../lib/know-v1";
import FixtureOfficialActions from "../../components/FixtureOfficialActions";
import type { OfficialChannels } from "../../../lib/official-channels";

type BoardPost = {
  post_id: number; parent_post_id: number | null; body: string; deleted: boolean;
  can_delete: boolean; can_report: boolean; created_at: string;
  author: { username: string | null; display_name: string; supported_club: string | null };
  replies?: BoardPost[];
};

type DecisionReason = {
  key: string; emoji: string; label: string; explanation: string; importance: string;
};

type SocialFixture = {
  fixture: { fixture_id: number; fixture_date: string; home_team: string; home_team_id: number | null; home_team_badge_url: string | null; away_team: string; away_team_id: number | null; away_team_badge_url: string | null; league_name: string; venue_id: number | null; venue_name: string | null; venue_city: string | null; status: string | null; home_goals: number | null; away_goals: number | null };
  terrace_rating: number | null; recommend_percentage: number | null;
  decision_reasons: DecisionReason[]; highlight_eligible: boolean;
  ticket_action: { label: string; url: string; source_label: string } | null;
  official_channels?: OfficialChannels | null;
  ticket_guidance: { label: string; message: string; source_label: string } | null;
  interested: boolean; open_to_meet: boolean; open_to_meet_count: number;
  profile: { username: string | null; display_name: string; supported_club: string | null } | null;
  own_review: { review_id: number; fixture_id: number | null; state: "blank" | "partial" | "completed"; completed: boolean } | null;
  own_attendance: { attended: boolean; visit_id: number | null; venue_id?: number; visit_date?: string | null };
  board_closed: boolean; posts: BoardPost[];
};

export default function FixturePage({ params, searchParams }: { params: Promise<{ fixtureId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { fixtureId } = use(params);
  const pendingSearchParams = use(searchParams);
  const router = useRouter();
  const [data, setData] = useState<SocialFixture | null>(null);
  const [error, setError] = useState("");
  const [body, setBody] = useState("");
  const [replyingTo, setReplyingTo] = useState<number | null>(null);
  const [isAnonymous, setIsAnonymous] = useState(true);
  const [accountPrompt, setAccountPrompt] = useState<"interested" | "mate" | "board" | null>(null);
  const [saving, setSaving] = useState(false);
  const [know, setKnow] = useState<FixtureKnowData | null>(null);
  const [reporting, setReporting] = useState<number | null>(null);
  const [reportReason, setReportReason] = useState("other");
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const pendingActionStarted = useRef(false);

  const load = useCallback(
    () => api.get<SocialFixture>(`/fixtures/${fixtureId}/social`).then((response) => {
      setData(response.data);
      return response.data;
    }),
    [fixtureId]
  );

  const requestMessage = (requestError: unknown, fallback: string) => {
    if (!axios.isAxiosError(requestError)) return fallback;
    const detail = requestError.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") return detail.message;
    return fallback;
  };

  useEffect(() => {
    api.get("/session").then((response) => {
      setIsAnonymous(response.data.anonymous !== false);
      return load();
    }).catch(() => setError("We couldn't load this match. Try again."));
  }, [load]);

  useEffect(() => {
    if (!data) return;
    api.get<FixtureKnowData>(`/fixtures/${fixtureId}/know`)
      .then((response) => setKnow(response.data))
      .catch(() => setKnow(null));
  }, [data, fixtureId]);

  useEffect(() => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(pendingSearchParams)) {
      if (typeof value === "string") params.set(key, value);
    }
    const numericFixtureId = Number(fixtureId);
    const hasUrlAction = hasPendingAuthAction(params);
    const pending = (hasUrlAction ? parsePendingWhosGoingAction(params, numericFixtureId) : null)
      ?? loadPendingWhosGoing(numericFixtureId);
    if ((!hasUrlAction && !pending) || pendingActionStarted.current) return;
    if (!pending) {
      pendingActionStarted.current = true;
      window.setTimeout(() => setError("Your saved Who's Going action expired or could not be verified. Use the button below to try again."), 0);
      router.replace(`/fixture/${fixtureId}`);
      return;
    }
    if (!data || isAnonymous || !data.profile?.username) return;

    pendingActionStarted.current = true;
    void applyPendingWhosGoing(
      pending,
      (pendingFixtureId) => api.put(`/fixtures/${pendingFixtureId}/open-to-meet`, { open_to_meet: true }).then((response) => response.data),
      load,
    )
      .then(() => {
        clearPendingWhosGoing();
        router.replace(`/fixture/${fixtureId}`);
      })
      .catch((requestError) => setError(requestMessage(requestError, "Your account is ready, but we couldn't enable Who's Going. Try the button again.")))
      ;
  }, [data, fixtureId, isAnonymous, load, pendingSearchParams, router]);

  const toggleInterested = async () => {
    if (!data || saving) return;
    setSaving(true); setError("");
    try {
      if (data.interested) await api.delete(`/fixtures/${fixtureId}/interested`);
      else {
        await api.post(`/fixtures/${fixtureId}/interested`);
        if (isAnonymous) setAccountPrompt("interested");
      }
      await load();
    } catch { setError("We couldn't update Interested. Try again."); }
    finally { setSaving(false); }
  };

  const toggleMeeting = async () => {
    if (!data || saving) return;
    if (isAnonymous && !data.open_to_meet) { setAccountPrompt("mate"); return; }
    if (!data.profile?.username) { router.push(accountRoute("/account/onboarding", `/fixture/${fixtureId}`)); return; }
    setSaving(true); setError("");
    try {
      const response = await api.put(`/fixtures/${fixtureId}/open-to-meet`, { open_to_meet: !data.open_to_meet });
      setData((current) => current ? { ...current, interested: response.data.interested, open_to_meet: response.data.open_to_meet, open_to_meet_count: response.data.open_to_meet_count } : current);
    } catch (requestError) { setError(requestMessage(requestError, "We couldn't update Who's Going. Try again.")); }
    finally { setSaving(false); }
  };

  const postMessage = async () => {
    const trimmed = body.trim();
    if (!trimmed || trimmed.length > 500) { setError("Message must be 1 to 500 characters."); return; }
    setSaving(true); setError("");
    try {
      await api.post(`/fixtures/${fixtureId}/board/posts`, { body: trimmed, parent_post_id: replyingTo });
      setBody(""); setReplyingTo(null); await load();
    } catch (requestError: unknown) { setError(requestMessage(requestError, "We couldn't post that. Try again.")); }
    finally { setSaving(false); }
  };

  const submitPost = async () => {
    if (isAnonymous) { setAccountPrompt("board"); return; }
    if (!data?.profile?.username) { router.push(accountRoute("/account/onboarding", `/fixture/${fixtureId}`)); return; }
    await postMessage();
  };

  const startReply = (postId: number) => {
    if (isAnonymous) { setAccountPrompt("board"); return; }
    if (!data?.profile?.username) { router.push(accountRoute("/account/onboarding", `/fixture/${fixtureId}`)); return; }
    setReplyingTo(postId);
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const deletePost = async (postId: number) => { await api.delete(`/board/posts/${postId}`); await load(); };
  const reportPost = async (postId: number) => {
    try { await api.post(`/board/posts/${postId}/reports`, { reason: reportReason }); setReporting(null); }
    catch (requestError: unknown) { setError(requestMessage(requestError, "We couldn't report that post. Try again.")); }
  };

  if (!data) return <main className="mx-auto w-full max-w-5xl p-4 sm:p-6"><p className="tt-kicker">01 / Match</p><p className="mt-3 font-semibold" role={error ? "alert" : undefined}>{error || "Loading fixture…"}</p></main>;
  const kickoff = new Date(data.fixture.fixture_date);
  const statusGroup = fixtureStatusGroup(data.fixture.status);
  const decisionReasons = data.decision_reasons ?? [];
  const hasDecisionReasons = decisionReasons.length > 0;
  const completed = statusGroup === "finished";
  const finishedForSocial = fixtureHasFinishedForSocial(data.fixture.status, data.board_closed);
  const hasResult = completed && data.fixture.home_goals !== null && data.fixture.away_goals !== null;
  const renderPost = (post: BoardPost, reply = false) => (
    <article key={post.post_id} className={`${reply ? "ml-3 border-l-2 border-[var(--mg-green)] pl-4 sm:ml-6" : "border-t border-[var(--mg-rule)] py-5"} min-w-0`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs uppercase tracking-[0.08em]">
        <strong className="min-w-0 break-words text-[var(--brand-interactive)]">{post.author.display_name}{post.author.username && <span className="ml-2 font-semibold normal-case text-[var(--tt-muted)]">@{post.author.username}</span>}</strong><time className="text-[var(--tt-muted)]">{new Date(post.created_at).toLocaleString()}</time>
      </div>
      {post.author.supported_club && <p className="mt-1 text-xs text-[var(--tt-muted)]">Supports {post.author.supported_club}</p>}
      <p className={`mt-3 whitespace-pre-wrap break-words leading-7 ${post.deleted ? "italic text-[var(--tt-muted)]" : ""}`}>{post.body}</p>
      {!post.deleted && <div className="mt-3 flex flex-wrap gap-4 text-xs font-extrabold uppercase tracking-[0.08em]">
        {!reply && !data.board_closed && <button type="button" onClick={() => startReply(post.post_id)} className="min-h-11 text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">Reply</button>}
        {post.can_delete && <button type="button" onClick={() => deletePost(post.post_id)} className="min-h-11 underline decoration-2 underline-offset-4">Delete</button>}
        {post.can_report && <button type="button" onClick={() => setReporting(post.post_id)} className="min-h-11 underline decoration-2 underline-offset-4">Report</button>}
      </div>}
      {reporting === post.post_id && <div className="mt-2 flex flex-col gap-2 sm:flex-row"><label className="sr-only" htmlFor={`report-reason-${post.post_id}`}>Report reason</label><select id={`report-reason-${post.post_id}`} value={reportReason} onChange={(e) => setReportReason(e.target.value)} className="tt-control px-3"><option value="harassment">Harassment</option><option value="spam">Spam</option><option value="unsafe_meetup">Unsafe meetup behavior</option><option value="offensive">Offensive content</option><option value="other">Other</option></select><button type="button" onClick={() => reportPost(post.post_id)} className="mg-primary-action px-4">Submit report</button></div>}
      {post.replies?.map((item) => <div className="mt-3" key={item.post_id}>{renderPost(item, true)}</div>)}
    </article>
  );

  return <main className="mx-auto w-full min-w-0 max-w-6xl px-4 py-7 sm:px-6 sm:py-10 lg:px-8">
    <section aria-labelledby="fixture-heading" className="border-b-2 border-[var(--mg-ink)] pb-6 sm:pb-8">
      <p className="mg-section-label">01 / Match · {data.fixture.league_name}</p>
      <div className="mt-5 grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-end lg:gap-12">
        <div className="min-w-0">
          <h1 id="fixture-heading" className="sr-only">{data.fixture.home_team} versus {data.fixture.away_team}</h1>
          <FixtureTeams homeTeam={data.fixture.home_team} awayTeam={data.fixture.away_team} homeBadgeSrc={apiAssetUrl(data.fixture.home_team_badge_url)} awayBadgeSrc={apiAssetUrl(data.fixture.away_team_badge_url)} className="max-w-4xl" teamClassName="mg-display-page" badgeClassName="h-12 w-12 sm:h-[4.5rem] sm:w-[4.5rem]" separatorClassName="my-2.5 text-sm tracking-[0.2em] sm:my-3 sm:text-base" />
          {hasResult && <p className="mg-display-section mt-6 text-[var(--mg-green)]" aria-label={`Final score ${data.fixture.home_goals} to ${data.fixture.away_goals}`}>{data.fixture.home_goals}–{data.fixture.away_goals}</p>}
        </div>
        <dl className="grid grid-cols-2 gap-x-5 gap-y-3 border-t border-[var(--mg-rule)] pt-4 text-sm lg:grid-cols-1 lg:border-l lg:border-t-0 lg:pl-7 lg:pt-0">
          <div><dt className="mg-meta font-bold">Date</dt><dd className="mt-0.5 font-bold">{kickoff.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</dd></div>
          <div><dt className="mg-meta font-bold">Kick-off</dt><dd className="mt-0.5 font-bold">{kickoff.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</dd><dd className="mg-meta text-xs">Your current timezone</dd></div>
          {statusGroup !== "upcoming" && !completed && <div><dt className="mg-meta font-bold">Status</dt><dd className="mt-0.5 font-bold">{fixtureStatusLabel(data.fixture.status)}</dd></div>}
          <div className="col-span-2 lg:col-span-1"><dt className="mg-meta font-bold">Ground</dt><dd className="mt-0.5 min-w-0 break-words font-bold">{data.fixture.venue_name || "Ground to be confirmed"}{data.fixture.venue_city ? ` · ${data.fixture.venue_city}` : ""}</dd></div>
        </dl>
      </div>
    </section>

    <AccountConversionPrompt open={accountPrompt !== null} kind={accountPrompt ?? "interested"} onDismiss={() => setAccountPrompt(null)} returnTo={accountPrompt === "mate" ? pendingWhosGoingReturnTo(Number(fixtureId)) : undefined} />
    {error && <p role="alert" className="mt-4 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}

    <FixtureOfficialActions ticketAction={data.ticket_action} channels={data.official_channels} teamName={data.fixture.home_team} />
    {!data.ticket_action && data.ticket_guidance && <section className="mg-utility-panel mt-5 px-4 py-3 sm:mt-6 sm:px-5" aria-label="Tickets">
      <p className="mg-section-label">{data.ticket_guidance.label}</p>
      <p className="mt-1 font-semibold text-[var(--mg-ink)]">{data.ticket_guidance.message}</p>
    </section>}

    {hasDecisionReasons && <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="why-this-match-heading">
      <p className="mg-section-label">02 / Why this match</p>
      <div className="mg-editorial-accent mt-3 bg-[var(--mg-paper-light)] px-4 py-5 sm:px-6 sm:py-6 lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(16rem,0.65fr)] lg:gap-10">
        <div>
          <p className="mg-display-callout text-[var(--mg-green)]">Worth going for</p>
          <h2 id="why-this-match-heading" className="mg-display-section mt-2">{decisionReasons[0].label}</h2>
          <p className="mg-body mt-3 max-w-3xl">{decisionReasons[0].explanation}</p>
        </div>
        {decisionReasons.length > 1 && <ul className="mt-4 divide-y divide-[var(--mg-rule)] border-t border-[var(--mg-rule)] lg:mt-0 lg:border-l lg:border-t-0 lg:pl-7">
          {decisionReasons.slice(1).map((reason) => <li key={`${reason.key}-${reason.label}`} className="py-3 first:pt-0"><strong className="block text-sm font-extrabold">{reason.label}</strong><span className="mg-body mt-1 block text-[var(--mg-muted)]">{reason.explanation}</span></li>)}
        </ul>}
        <div className="mt-4 flex flex-wrap gap-1.5 lg:col-span-2">{decisionReasons.map((reason) => <span key={`tag-${reason.key}-${reason.label}`} className="mg-reason-stamp bg-[var(--mg-paper)]">{reason.label}</span>)}</div>
      </div>
    </section>}

    <FixtureKnow know={know} teamName={data.fixture.home_team} />

    {data.fixture.venue_id && <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="ground-heading">
      <p className="mg-section-label">06 / The ground</p>
      <div className="mt-3 grid gap-4 border-b border-[var(--mg-rule)] pb-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div className="min-w-0"><h2 id="ground-heading" className="mg-display-section break-words">{data.fixture.venue_name || "The ground"}</h2>{data.fixture.venue_city && <p className="mg-meta mt-3 font-bold">{data.fixture.venue_city}</p>}</div>
        <Link href={`/venue/${data.fixture.venue_id}${data.fixture.home_team_id ? `?teamId=${data.fixture.home_team_id}` : ""}`} className="mg-tertiary-action inline-flex items-center">Explore the ground →</Link>
      </div>
      {(data.terrace_rating !== null || data.recommend_percentage !== null) && <details className="mt-4 text-xs text-[var(--tt-muted)]"><summary className="cursor-pointer font-bold uppercase tracking-[0.08em]">Community ground ratings</summary><div className="mt-2 flex flex-wrap gap-x-6 gap-y-2">{data.terrace_rating !== null && <span>★ {data.terrace_rating.toFixed(1)} Terrace Rating</span>}{data.recommend_percentage !== null && <span>{Math.round(data.recommend_percentage)}% recommended</span>}</div></details>}
    </section>}

    {statusGroup === "cancelled" ? <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="matchday-heading"><p className="mg-section-label">07 / Social · Match update</p><h2 id="matchday-heading" className="mg-display-section mt-2">This match is cancelled</h2><p className="mg-body mt-3 max-w-2xl text-[var(--mg-muted)]">It won&apos;t appear as an upcoming plan or attendance option.</p>{data.interested && <button type="button" disabled={saving} onClick={toggleInterested} className="mg-secondary-action mt-4 px-5">Remove from Interested</button>}</section> : !finishedForSocial ? <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="matchday-heading">
      <div>
        <p className="mg-section-label">07 / Social · {statusGroup === "postponed" ? "Match update" : "Your matchday"}</p>
        <h2 id="matchday-heading" className="mg-display-section mt-2">{statusGroup === "postponed" ? "Match postponed" : "Make it yours"}</h2>
        {statusGroup === "postponed" && <p className="mt-3 text-[var(--tt-muted)]">Keep this on your radar while a new kickoff is confirmed.</p>}
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <button type="button" disabled={saving} aria-pressed={data.interested} onClick={toggleInterested} className={`${data.interested ? "mg-primary-action" : "mg-secondary-action"} px-5 py-3 text-left`}>{data.interested ? "✓ Interested" : "Interested"}</button>
          <button type="button" disabled={saving} aria-pressed={data.open_to_meet} onClick={toggleMeeting} className={`${data.open_to_meet ? "mg-primary-action" : "mg-secondary-action"} px-5 py-3 text-left`}>{data.open_to_meet ? "✓ Open to meeting supporters" : "Open to meeting supporters"}</button>
        </div>
        {data.open_to_meet_count > 0 && <p className="mt-3 text-xs font-bold text-[var(--tt-muted)]">{data.open_to_meet_count} {data.open_to_meet_count === 1 ? "supporter is" : "supporters are"} open to meeting.</p>}
        <p className="mt-2 text-xs leading-5 text-[var(--tt-muted)]">Meet safely in public matchday locations and use your judgment when meeting someone new.</p>
      </div>
    </section> : null}

    <section className="mg-editorial-rule mt-9 pt-3 sm:mt-10 sm:pt-4" aria-labelledby="board-heading">
      <p className="mg-section-label">08 / Social · Supporter correspondence</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3"><h2 id="board-heading" className="mg-display-section">Match Board</h2>{data.posts.length > 0 && <span className="text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--mg-muted)]">{data.posts.length} {data.posts.length === 1 ? "thread" : "threads"}</span>}</div>
      {data.board_closed ? <div className="mg-utility-panel mt-5 p-4 sm:p-5"><p className="mg-display-callout">The board is closed</p><p className="mt-2 text-[var(--mg-muted)]">{statusGroup === "cancelled" ? "This match was cancelled." : "This match has finished."}</p></div> : <div className="mg-utility-panel mt-5 p-4 sm:p-5">{data.posts.length === 0 && <p className="mb-4 max-w-2xl leading-7 text-[var(--mg-muted)]">Ask other supporters about the match, pubs, travel or the ground.</p>}<label htmlFor="match-board-message" className="mg-section-label">{replyingTo ? "Your reply" : "Post to the board"}</label><textarea id="match-board-message" ref={composerRef} value={body} onChange={(e) => setBody(e.target.value)} maxLength={500} rows={4} placeholder={replyingTo ? "Write a reply" : "Ask about travel, pubs, tickets or the ground…"} className="tt-control mt-2 w-full min-w-0 resize-y p-3"/><div className="mt-3 grid gap-3 sm:flex sm:items-center sm:justify-between"><span className="text-xs font-semibold text-[var(--mg-muted)]">{body.length} / 500</span><button type="button" disabled={saving || !body.trim()} onClick={submitPost} className="mg-primary-action w-full px-5 sm:w-auto">{replyingTo ? "Post reply" : "Post to board"}</button></div></div>}
      {data.posts.length > 0 && <div className="mt-6">{data.posts.map((post) => renderPost(post))}</div>}
    </section>

  </main>;
}
