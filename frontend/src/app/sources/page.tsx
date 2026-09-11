"use client";

import { useEffect, useState } from "react";
import { api, type Competition, type DataSource } from "@/lib/api";

export default function SourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [comps, setComps] = useState<Competition[]>([]);
  useEffect(() => { api.dataSources().then(setSources).catch(() => null); api.competitions().then(setComps).catch(() => null); }, []);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Data sources, licences and coverage</h1>
      {sources.map((s) => (
        <section key={s.code} className={`card p-5 text-sm ${s.is_active ? "" : "opacity-70"}`}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-semibold">{s.name} <span className="ml-2 font-mono text-xs text-muted">{s.code}</span></h2>
            <span className={`text-xs ${s.is_active ? "text-good" : "text-muted"}`}>{s.is_active ? "active" : "not wired"}{s.requires_api_key ? " · API key required" : ""}</span>
          </div>
          <div className="mt-1 text-xs text-ink-2">{s.url} · {s.data_types.join(", ")} · updates: {s.update_frequency} · reliability {s.reliability_score ?? "—"}</div>
          <p className="mt-2 text-ink-2">{s.licence}</p>
          <div className="mt-2 grid gap-1 text-xs text-muted md:grid-cols-3">
            <div>commercial use: {s.commercial_use_allowed == null ? "unverified" : s.commercial_use_allowed ? "allowed" : "not allowed"}</div>
            <div>redistribution: {s.redistribution_allowed == null ? "unverified" : s.redistribution_allowed ? "allowed" : "not allowed"}</div>
            <div>attribution: {s.attribution_required ? s.attribution_text : "not required"}</div>
          </div>
          {s.notes && <p className="mt-2 text-xs text-muted">{s.notes}</p>}
        </section>
      ))}
      <section className="card p-5 text-sm">
        <h2 className="mb-2 font-semibold">Competitions loaded</h2>
        <table className="w-full"><thead><tr className="label text-left"><th>competition</th><th>country</th><th>gender</th><th>type</th><th className="text-right">seasons</th><th className="text-right">matches</th><th>latest strength</th></tr></thead>
          <tbody>{comps.map((c) => { const s0 = c.seasons[0]; return (
            <tr key={c.competition_id} className="border-b border-border/40"><td className="py-1">{c.name}</td><td>{c.country ?? c.region}</td><td>{c.gender}</td><td className="text-xs">{c.type}</td><td className="text-right tabular">{c.seasons.length}</td><td className="text-right tabular">{c.matches}</td>
              <td className="text-xs">{s0?.league_strength == null ? "—" : `${s0.league_strength.toFixed(2)} (${s0.league_strength_confidence}${s0.league_strength_is_prior ? ", prior" : ""})`}</td></tr>); })}</tbody></table>
      </section>
    </div>
  );
}
