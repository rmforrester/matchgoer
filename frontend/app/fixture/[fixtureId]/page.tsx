"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import api from "../../../lib/api";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../../lib/fixture-status";
import AccountConversionPrompt from "../../components/AccountConversionPrompt";
import FixtureTeams from "../../components/FixtureTeams";
import { accountRoute } from "@/lib/auth-flow";
import { hasPendingAuthAction, parsePendingWhosGoingAction, pendingWhosGoingReturnTo } from "@/lib/pending-auth-action";
import { applyPendingWhosGoing, clearPendingWhosGoing, loadPendingWhosGoing } from "@/lib/account-conversion-checkpoint";
import { fixtureGuideActions, guideSummary, type VenueGuide } from "../../../lib/venue-guide";

type BoardPost = {
  post_id: number; parent_post_id: number | null; body: string; deleted: boolean;
  can_delete: boolean; can_report: boolean; created_at: string;
  author: { username: string | null; display_name: string; supported_club: string | null };
  replies?: BoardPost[];
};

type SocialFixture = {
  fixture: { fixture_id: number; fixture_date: string; home_team: string; away_team: string; league_name: string; venue_id: number | null; venue_name: string | null; venue_city: string | null; status: string | null; home_goals: number | null; away_goals: number | null };
  terrace_rating: number | null; recommend_percentage: number | null;
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
  const [venueGuideResult, setVenueGuideResult] = useState<{ venueId: number; guide: VenueGuide | null } | null>(null);
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
    }).catch(() => setError("Unable to load this fixture."));
  }, [load]);

  useEffect(() => {
    const venueId = data?.fixture.venue_id;
    if (!venueId) return;
    api.get<VenueGuide>(`/venues/${venueId}/guide`)
      .then((response) => setVenueGuideResult({ venueId, guide: response.data }))
      .catch(() => setVenueGuideResult({ venueId, guide: null }));
  }, [data?.fixture.venue_id]);

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
      .catch((requestError) => setError(requestMessage(requestError, "Your account is ready, but we couldn't enable Who's Going?. Try the button again.")))
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
    } catch { setError("Unable to update Interested."); }
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
    } catch (requestError) { setError(requestMessage(requestError, "Unable to update Who's Going?.")); }
    finally { setSaving(false); }
  };

  const postMessage = async () => {
    const trimmed = body.trim();
    if (!trimmed || trimmed.length > 500) { setError("Message must be 1 to 500 characters."); return; }
    setSaving(true); setError("");
    try {
      await api.post(`/fixtures/${fixtureId}/board/posts`, { body: trimmed, parent_post_id: replyingTo });
      setBody(""); setReplyingTo(null); await load();
    } catch (requestError: unknown) { setError(requestMessage(requestError, "Unable to post.")); }
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
    catch (requestError: unknown) { setError(requestMessage(requestError, "Unable to report this post.")); }
  };

  const recordAttendance = async () => {
    if (!data?.fixture.venue_id || saving || data.own_attendance.attended) return;
    setSaving(true); setError("");
    try {
      await api.post(`/fixtures/${fixtureId}/attendance`);
      await load();
    } catch (requestError) {
      setError(requestMessage(requestError, "Unable to record your attendance."));
    } finally {
      setSaving(false);
    }
  };

  const removeAttendance = async () => {
    if (!data?.own_attendance.attended || saving) return;
    setSaving(true); setError("");
    try {
      await api.delete(`/fixtures/${fixtureId}/attendance`);
      await load();
    } catch (requestError) {
      setError(requestMessage(requestError, "Unable to remove your attendance."));
    } finally {
      setSaving(false);
    }
  };

  const openPostMatchReview = async () => {
    if (!data?.fixture.venue_id || saving) return;
    setSaving(true); setError("");
    try {
      if (!data.own_review) {
        await api.post(`/venues/${data.fixture.venue_id}/away-day-reviews`, {
          venue_id: data.fixture.venue_id,
          fixture_id: data.fixture.fixture_id,
        });
      }
      router.push(`/my-football?tab=visited&review=${data.fixture.venue_id}`);
    } catch (requestError) {
      if (axios.isAxiosError(requestError) && requestError.response?.status === 409) {
        router.push(`/my-football?tab=visited&review=${data.fixture.venue_id}`);
        return;
      }
      setError(requestMessage(requestError, "Unable to open this matchday review."));
      setSaving(false);
    }
  };

  if (!data) return <main className="mx-auto w-full max-w-5xl p-4 sm:p-6"><p className="tt-kicker">01 / Match</p><p className="mt-3 font-semibold" role={error ? "alert" : undefined}>{error || "Loading fixture…"}</p></main>;
  const kickoff = new Date(data.fixture.fixture_date);
  const statusGroup = fixtureStatusGroup(data.fixture.status);
  const venueGuide = venueGuideResult?.venueId === data.fixture.venue_id ? venueGuideResult.guide : null;
  const knowSummary = guideSummary(venueGuide);
  const knowActions = venueGuide && data.fixture.venue_id ? fixtureGuideActions(venueGuide, data.fixture.venue_id) : [];
  const completed = statusGroup === "finished";
  const hasResult = completed && data.fixture.home_goals !== null && data.fixture.away_goals !== null;
  const renderPost = (post: BoardPost, reply = false) => (
    <article key={post.post_id} className={`${reply ? "ml-3 border-l-2 border-[var(--tt-blue)] pl-4 sm:ml-6" : "border-t-2 border-[var(--tt-ink)] py-5"} min-w-0`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs uppercase tracking-[0.08em]">
        <strong className="min-w-0 break-words text-[var(--tt-blue)]">{post.author.display_name}{post.author.username && <span className="ml-2 font-semibold normal-case text-[var(--tt-muted)]">@{post.author.username}</span>}</strong><time className="text-[var(--tt-muted)]">{new Date(post.created_at).toLocaleString()}</time>
      </div>
      {post.author.supported_club && <p className="mt-1 text-xs text-[var(--tt-muted)]">Supports {post.author.supported_club}</p>}
      <p className={`mt-3 whitespace-pre-wrap break-words leading-7 ${post.deleted ? "italic text-[var(--tt-muted)]" : ""}`}>{post.body}</p>
      {!post.deleted && <div className="mt-3 flex flex-wrap gap-4 text-xs font-extrabold uppercase tracking-[0.08em]">
        {!reply && !data.board_closed && <button type="button" onClick={() => startReply(post.post_id)} className="min-h-11 text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Reply</button>}
        {post.can_delete && <button type="button" onClick={() => deletePost(post.post_id)} className="min-h-11 underline decoration-2 underline-offset-4">Delete</button>}
        {post.can_report && <button type="button" onClick={() => setReporting(post.post_id)} className="min-h-11 underline decoration-2 underline-offset-4">Report</button>}
      </div>}
      {reporting === post.post_id && <div className="mt-2 flex flex-col gap-2 sm:flex-row"><label className="sr-only" htmlFor={`report-reason-${post.post_id}`}>Report reason</label><select id={`report-reason-${post.post_id}`} value={reportReason} onChange={(e) => setReportReason(e.target.value)} className="tt-control px-3"><option value="harassment">Harassment</option><option value="spam">Spam</option><option value="unsafe_meetup">Unsafe meetup behavior</option><option value="offensive">Offensive content</option><option value="other">Other</option></select><button type="button" onClick={() => reportPost(post.post_id)} className="tt-action px-4">Submit report</button></div>}
      {post.replies?.map((item) => <div className="mt-3" key={item.post_id}>{renderPost(item, true)}</div>)}
    </article>
  );

  return <main className="mx-auto w-full min-w-0 max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
    <section aria-labelledby="fixture-heading" className="tt-panel overflow-hidden">
      <div className="border-b-2 border-[var(--tt-ink)] bg-[var(--tt-blue)] px-4 py-3 text-[var(--tt-paper)] sm:px-7">
        <p className="text-xs font-extrabold uppercase tracking-[0.14em]">01 / Match · {data.fixture.league_name}</p>
      </div>
      <div className="grid min-w-0 gap-6 px-4 py-6 sm:px-7 sm:py-8 lg:grid-cols-[minmax(0,1fr)_17rem] lg:items-end">
        <div className="min-w-0">
          <h1 id="fixture-heading" className="sr-only">{data.fixture.home_team} versus {data.fixture.away_team}</h1>
          <FixtureTeams homeTeam={data.fixture.home_team} awayTeam={data.fixture.away_team} className="max-w-3xl" teamClassName="text-[clamp(2.5rem,9vw,5.75rem)] leading-[0.82]" separatorClassName="my-2 text-sm tracking-[0.18em] sm:text-base" />
          {hasResult && <p className="tt-display mt-5 text-5xl leading-none text-[var(--tt-blue)]" aria-label={`Final score ${data.fixture.home_goals} to ${data.fixture.away_goals}`}>{data.fixture.home_goals}–{data.fixture.away_goals}</p>}
        </div>
        <dl className="grid gap-3 border-t-2 border-[var(--tt-ink)] pt-4 text-sm lg:border-l-2 lg:border-t-0 lg:pl-6 lg:pt-0">
          <div><dt className="tt-kicker">Date</dt><dd className="mt-1 font-bold">{kickoff.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</dd></div>
          <div><dt className="tt-kicker">Kickoff</dt><dd className="mt-1 font-bold">{kickoff.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</dd></div>
          {statusGroup !== "upcoming" && <div><dt className="tt-kicker">Status</dt><dd className="mt-1 font-bold">{fixtureStatusLabel(data.fixture.status)}</dd></div>}
          <div><dt className="tt-kicker">Ground</dt><dd className="mt-1 min-w-0 break-words font-bold">{data.fixture.venue_name || "Ground to be confirmed"}{data.fixture.venue_city ? ` · ${data.fixture.venue_city}` : ""}</dd></div>
        </dl>
      </div>
    </section>

    <AccountConversionPrompt open={accountPrompt !== null} kind={accountPrompt ?? "interested"} onDismiss={() => setAccountPrompt(null)} returnTo={accountPrompt === "mate" ? pendingWhosGoingReturnTo(Number(fixtureId)) : undefined} />
    {error && <p role="alert" className="mt-4 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}

    {knowSummary && data.fixture.venue_id && <aside className="tt-panel mt-6 border-l-[8px] border-l-[var(--tt-blue)] p-5" aria-labelledby="know-before-heading">
      <p className="tt-kicker">Know before you go</p>
      <h2 id="know-before-heading" className="tt-display mt-1 text-3xl leading-none">{data.fixture.venue_name ?? "Plan this matchday"}</h2>
      <nav aria-label="Matchday planning" className="mt-4 flex flex-wrap gap-x-5 gap-y-3 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)]">
        {knowActions.map((action) => action.external
          ? <a key={action.label} href={action.href} target="_blank" rel="noreferrer" className="underline decoration-2 underline-offset-4">{action.label} →</a>
          : <Link key={action.label} href={action.href} className="underline decoration-2 underline-offset-4">{action.label} →</Link>)}
      </nav>
    </aside>}

    {completed ? <section className="tt-section-rule mt-8 pt-4" aria-labelledby="matchday-heading">
      <p className="tt-kicker">02 / Did you go?</p>
      <div className="mt-1 grid gap-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div><h2 id="matchday-heading" className="tt-display text-4xl leading-none sm:text-5xl">{data.own_attendance.attended ? "✓ Attendance recorded" : "Did you go?"}</h2><p className="mt-3 max-w-2xl text-[var(--tt-muted)]">{data.fixture.venue_id ? data.own_attendance.attended ? "This match is in your attended history. Rating the ground and adding a supporter tip are optional." : "Record the match now. You can rate the ground or leave a tip separately." : "This fixture is not linked to a ground, so attendance cannot be recorded yet."}</p></div>
        {data.fixture.venue_id && !data.own_attendance.attended && <button type="button" disabled={saving} onClick={recordAttendance} className="tt-action px-5">{saving ? "Recording…" : "Yes — I was there"}</button>}
      </div>
      {data.own_attendance.attended && data.fixture.venue_id && <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-[var(--tt-rule)] pt-4 text-xs font-extrabold uppercase tracking-[0.08em]"><button type="button" disabled={saving} onClick={openPostMatchReview} className="text-[var(--tt-blue)] underline decoration-2 underline-offset-4">{data.own_review?.state === "completed" ? "Edit my review →" : data.own_review?.state === "partial" ? "Continue review →" : "Rate the ground →"}</button><Link href={`/venue/${data.fixture.venue_id}#tips-add`} className="text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Add a tip →</Link><button type="button" disabled={saving} onClick={removeAttendance} className="text-[var(--tt-muted)] underline decoration-2 underline-offset-4">Remove attendance</button></div>}
    </section> : statusGroup === "cancelled" ? <section className="tt-section-rule mt-8 pt-4" aria-labelledby="matchday-heading"><p className="tt-kicker">02 / Match update</p><h2 id="matchday-heading" className="tt-display mt-1 text-4xl leading-none sm:text-5xl">This match is cancelled</h2><p className="mt-3 max-w-2xl text-[var(--tt-muted)]">It will not be treated as an upcoming plan or attendance opportunity.</p>{data.interested && <button type="button" disabled={saving} onClick={toggleInterested} className="tt-action tt-action-secondary mt-4 px-5">Remove from Interested</button>}</section> : <section className="tt-section-rule mt-8 grid gap-5 pt-4 lg:grid-cols-[minmax(0,1fr)_18rem]" aria-labelledby="matchday-heading">
      <div>
        <p className="tt-kicker">02 / {statusGroup === "postponed" ? "Match update" : "Your matchday"}</p>
        <h2 id="matchday-heading" className="tt-display mt-1 text-4xl leading-none sm:text-5xl">{statusGroup === "postponed" ? "Match postponed" : "Make it yours"}</h2>
        {statusGroup === "postponed" && <p className="mt-3 text-[var(--tt-muted)]">Keep this on your radar while a new kickoff is confirmed.</p>}
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <button type="button" disabled={saving} aria-pressed={data.interested} onClick={toggleInterested} className={`tt-action px-5 py-3 text-left ${data.interested ? "bg-[var(--tt-blue)]" : "tt-action-secondary"}`}>{data.interested ? "✓ Interested" : "Interested"}</button>
          <button type="button" disabled={saving} aria-pressed={data.open_to_meet} onClick={toggleMeeting} className={`tt-action px-5 py-3 text-left ${data.open_to_meet ? "bg-[var(--tt-blue)]" : "tt-action-secondary"}`}>{data.open_to_meet ? "✓ Open to meeting supporters" : "Who's Going?"}</button>
        </div>
      </div>
      <aside className="tt-panel self-end p-4" aria-label="Matchday community">
        <p className="tt-kicker">Terrace roll call</p>
        <p className="tt-display mt-2 text-3xl leading-none">Who&apos;s Going? · {data.open_to_meet_count}</p>
        <p className="mt-3 text-xs leading-5 text-[var(--tt-muted)]">Meet safely in public matchday locations and use your judgment when meeting someone new.</p>
      </aside>
    </section>}

    <section className="tt-section-rule mt-10 pt-4" aria-labelledby="board-heading">
      <p className="tt-kicker">03 / Supporter correspondence</p>
      <div className="mt-1 flex flex-wrap items-end justify-between gap-3"><h2 id="board-heading" className="tt-display text-4xl leading-none sm:text-5xl">Match Board</h2><span className="text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-muted)]">{data.posts.length} {data.posts.length === 1 ? "thread" : "threads"}</span></div>
      {data.board_closed ? <div className="tt-panel mt-5 p-4 sm:p-5"><p className="tt-display text-2xl">The board is closed</p><p className="mt-2 text-[var(--tt-muted)]">{statusGroup === "cancelled" ? "This match was cancelled." : "This match has finished."}</p></div> : <div className="tt-panel mt-5 p-4 sm:p-5">{data.posts.length === 0 && <p className="mb-4 max-w-2xl leading-7 text-[var(--tt-muted)]">Going to this one? Ask about pubs, travel, the ground, or see who else is heading along.</p>}<label htmlFor="match-board-message" className="tt-kicker">{replyingTo ? "Your reply" : "Post to the board"}</label><textarea id="match-board-message" ref={composerRef} value={body} onChange={(e) => setBody(e.target.value)} maxLength={500} rows={4} placeholder={replyingTo ? "Write a reply" : "Ask about travel, pubs, tickets or the ground…"} className="tt-control mt-2 w-full min-w-0 resize-y p-3"/><div className="mt-3 grid gap-3 sm:flex sm:items-center sm:justify-between"><span className="text-xs font-semibold text-[var(--tt-muted)]">{body.length} / 500</span><button type="button" disabled={saving || !body.trim()} onClick={submitPost} className="tt-action w-full px-5 sm:w-auto">{replyingTo ? "Post reply" : "Post to board"}</button></div></div>}
      {data.posts.length > 0 && <div className="mt-6">{data.posts.map((post) => renderPost(post))}</div>}
    </section>

    {data.fixture.venue_id && <section className="tt-section-rule mt-10 pt-4" aria-labelledby="ground-heading">
      <p className="tt-kicker">04 / The ground</p>
      <div className="mt-2 grid gap-4 border-b-2 border-[var(--tt-ink)] pb-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <div className="min-w-0"><h2 id="ground-heading" className="tt-display break-words text-4xl leading-none sm:text-5xl">{data.fixture.venue_name || "The ground"}</h2>{data.fixture.venue_city && <p className="mt-2 font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{data.fixture.venue_city}</p>}</div>
        <Link href={`/venue/${data.fixture.venue_id}`} className="tt-action inline-flex items-center justify-center px-5">Explore the ground →</Link>
      </div>
      {(data.terrace_rating !== null || data.recommend_percentage !== null) && <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs font-extrabold uppercase tracking-[0.08em]">{data.terrace_rating !== null && <span>★ {data.terrace_rating.toFixed(1)} Terrace Rating</span>}{data.recommend_percentage !== null && <span>{Math.round(data.recommend_percentage)}% recommended</span>}</div>}
    </section>}
  </main>;
}
