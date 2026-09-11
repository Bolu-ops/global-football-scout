"use client";

import { useEffect, useState } from "react";
import { api, type AdminStats, type Coverage, type Job } from "@/lib/api";

export default function AdminPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [coverage, setCoverage] = useState<Coverage[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.adminStats().then(setStats).catch((e) => setError(String(e)));
    api.adminJobs().then(setJobs).catch(() => null);
    api.coverage().then(setCoverage).catch(() => null);
  }, []);

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
