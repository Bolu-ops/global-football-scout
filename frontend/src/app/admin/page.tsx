"use client";

import { useEffect, useState } from "react";
import { api, type AdminStats, type Coverage, type IdentityReview, type Job } from "@/lib/api";

export default function AdminPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [coverage, setCoverage] = useState<Coverage[]>([]);
  const [reviews, setReviews] = useState<IdentityReview[]>([]);
  // The review queue and its decisions need the server's ADMIN_TOKEN; kept for this tab only.
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [reviewError, setReviewError] = useState<string | null>(null);
  async function decide(id: number, d: "approve" | "reject") {
    try {
      await api.decideIdentity(id, d, token);
      setReviews((r) => r.filter((x) => x.candidate_id !== id));
    } catch (e) {
      setReviewError(String(e));
    }
  }
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.adminStats().then(setStats).catch((e) => setError(String(e)));
    api.adminJobs().then(setJobs).catch(() => null);
    api.coverage().then(setCoverage).catch(() => null);
    let saved: string | null = null;
    try {
      saved = sessionStorage.getItem("gfs-admin-token");
    } catch {
      /* storage unavailable: ask again */
    }
    if (saved) loadReviews(saved);
  }, []);

  function loadReviews(t: string) {
    api
      .identityReviews(t)
      .then((r) => {
        setToken(t);
        setReviewError(null);
        setReviews(r);
      })
      .catch((e) => {
        setToken(t);
        setReviews([]);
        setReviewError(String(e).includes("401") ? "Admin token rejected." : String(e));
      });
  }

  function saveToken(e: React.FormEvent) {
    e.preventDefault();
    try {
      sessionStorage.setItem("gfs-admin-token", tokenInput);
    } catch {
      /* keep it in memory only */
    }
    loadReviews(tokenInput);
    setTokenInput("");
  }

  if (error) return <div className="text-bad">{error}</div>;
  if (!stats) return <div className="text-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Data engineering dashboard</h1>
      <p className="text-sm text-muted">All numbers are live counts from the database (config {stats.config_version}).</p>
      <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {Object.entries(stats.counts).map(([k, v]) => (
          <div key={k} className="card p-4">
            <div className="label">{k.replaceAll("_", " ")}</div>
            <div className="mt-1 text-2xl font-semibold tabular">{v.toLocaleString()}</div>
          </div>
        ))}
      </section>
      <section className="grid gap-3 md:grid-cols-4">
        <Tile label="failed jobs" value={stats.failed_jobs} />
        <Tile label="running jobs" value={stats.last_ingestion?.running_jobs ?? 0} />
        <Tile label="pending identity reviews" value={stats.pending_identity_reviews} />
        <Tile label="open quality flags" value={stats.open_quality_flags} />
      </section>
      <section className="card p-4">
        <h2 className="mb-2 font-semibold">Excluded leagues (amendment A1)</h2>
        <ul className="text-sm">
          {stats.excluded_competitions.map((c) => (
            <li key={c.competition_id} className="flex justify-between border-b border-border/40 py-1">
              <span>{c.name} <span className="text-muted">({c.country})</span></span>
              <span className="tabular text-ink-2">{c.score.toFixed(3)} · {c.basis} · {c.confidence}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="card p-4">
        <h2 className="mb-2 font-semibold">Data sources</h2>
        <table className="w-full text-sm">
          <thead><tr className="label text-left"><th>code</th><th>name</th><th>active</th><th>key required</th><th className="text-right">jobs</th></tr></thead>
          <tbody>{stats.sources.map((s) => (
            <tr key={s.code} className="border-b border-border/40"><td className="py-1 font-mono text-xs">{s.code}</td><td>{s.name}</td><td>{s.is_active ? "yes" : "no"}</td><td>{s.requires_api_key ? "yes" : "no"}</td><td className="text-right tabular">{s.jobs}</td></tr>
          ))}</tbody>
        </table>
      </section>
      <section className="card p-4">
        <h2 className="mb-1 font-semibold">Identity review queue</h2>
        <p className="mb-2 text-xs text-muted">Cross-source matches that were not unambiguous. Approving copies the source&apos;s biographical data onto the player; nothing is merged automatically.</p>
        <form onSubmit={saveToken} className="mb-2 flex flex-wrap items-center gap-2 text-sm">
          <input type="password" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} placeholder={token ? "Admin token set" : "Admin token"} aria-label="Admin token" className="rounded border border-border bg-transparent px-2 py-1" />
          <button type="submit" className="rounded border border-border px-2 py-1">Unlock</button>
        </form>
        {reviewError && <p className="mb-2 text-sm text-bad">{reviewError}</p>}
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-sm">
            <thead><tr className="label text-left"><th>internal player</th><th>source candidate</th><th className="text-right">score</th><th>why review</th><th></th></tr></thead>
            <tbody>{reviews.map((r) => (
              <tr key={r.candidate_id} className="border-b border-border/40">
                <td className="py-1">{r.internal_name} <span className="text-xs text-muted">({r.internal_full_name})</span></td>
                <td className="text-xs">{String(r.components.label ?? "")} · born {String(r.components.dob ?? "?")} · <span className="font-mono">{r.source_player_id}</span></td>
                <td className="text-right tabular">{r.score.toFixed(2)}</td>
                <td className="text-xs text-muted">{r.components.ambiguous ? `ambiguous (${(r.components.ambiguous as string[]).length} candidates)` : r.components.possible_duplicate_of_player_id ? `possible duplicate of player ${String(r.components.possible_duplicate_of_player_id)}` : r.components.fuzzy ? `fuzzy name match ${Number(r.components.fuzzy).toFixed(2)}` : ""}</td>
                <td className="whitespace-nowrap text-right"><button onClick={() => decide(r.candidate_id, "approve")} className="mr-2 text-good">approve</button><button onClick={() => decide(r.candidate_id, "reject")} className="text-bad">reject</button></td>
              </tr>
            ))}</tbody>
          </table>
          {!token && <p className="text-sm text-muted">Enter the admin token to see the queue.</p>}
          {token && !reviewError && reviews.length === 0 && <p className="text-sm text-muted">Queue empty.</p>}
        </div>
      </section>
      <section className="card p-4">
        <h2 className="mb-2 font-semibold">Ingestion jobs</h2>
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-sm">
            <thead><tr className="label text-left"><th>id</th><th>type</th><th>params</th><th>status</th><th>started</th><th className="text-right">written</th><th className="text-right">failed items</th></tr></thead>
            <tbody>{jobs.map((j) => (
              <tr key={j.job_id} className="border-b border-border/40">
                <td className="py-1 tabular">{j.job_id}</td><td className="font-mono text-xs">{j.job_type}</td>
                <td className="text-xs text-ink-2">{String(j.params.competition ?? "")} {String(j.params.season ?? "")}{j.params.years ? ` years ${String(j.params.years)}` : ""}</td>
                <td className={j.status === "failed" ? "text-bad" : j.status === "succeeded" ? "text-good" : "text-warn"}>{j.status}</td>
                <td className="text-xs text-muted">{new Date(j.started_at).toLocaleString()}</td>
                <td className="text-right tabular">{j.rows_written}</td><td className="text-right tabular">{j.failed_items}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>
      <section className="card p-4">
        <h2 className="mb-2 font-semibold">Coverage by competition-season</h2>
        <div className="max-h-[32rem] overflow-auto">
          <table className="w-full text-sm">
            <thead><tr className="label text-left"><th>competition</th><th>gender</th><th>type</th><th>season</th><th>coverage</th><th>note</th><th className="text-right">matches</th></tr></thead>
            <tbody>{coverage.map((c, i) => (
              <tr key={i} className="border-b border-border/40"><td className="py-1">{c.competition}</td><td>{c.gender}</td><td className="text-xs">{c.type}</td><td>{c.season}</td><td className={c.coverage === "single_team" ? "text-warn" : ""}>{c.coverage}</td><td className="text-xs text-muted">{c.note}</td><td className="text-right tabular">{c.matches}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return <div className="card p-4"><div className="label">{label}</div><div className="mt-1 text-2xl font-semibold tabular">{value}</div></div>;
}
