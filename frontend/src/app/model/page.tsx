"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ModelPage() {
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  useEffect(() => { api.modelInfo().then(setInfo).catch(() => null); }, []);
  if (!info) return <div className="text-muted">Loading…</div>;
  const sim = info.similarity as Record<string, unknown>;
  const ls = info.league_strength as Record<string, unknown>;
  const ex = info.exclusion_rule as { description: string; excluded: { name: string; score: number; basis: string }[]; full_ranking: { name: string; score: number; basis: string; confidence: string }[] };
  const tv = info.transfer_value as { status: string; note: string };
  const pct = info.percentiles as Record<string, unknown>;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Methodology &amp; model transparency</h1>
      <Section title="Principles"><ul className="list-disc pl-5">{(info.principles as string[]).map((p) => <li key={p}>{p}</li>)}</ul></Section>
      <Section title="Similarity engine">
        <ol className="list-decimal pl-5">{(sim.pipeline as string[]).map((p) => <li key={p}>{p}</li>)}</ol>
        <p className="mt-2 text-xs text-muted">delta = {String(sim.delta)} · results returned = {String(sim.result_count)}</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {Object.entries(sim.category_weights as Record<string, Record<string, number>>).map(([g, w]) => (
            <div key={g} className="rounded bg-surface-2 p-2 text-xs"><div className="mb-1 font-mono">{g}</div>{Object.entries(w).map(([c, v]) => <div key={c} className="flex justify-between"><span>{c}</span><span className="tabular">{v}</span></div>)}</div>
          ))}
        </div>
      </Section>
      <Section title="League strength">
        <p>{String(ls.adjustment)}</p>
        <ul className="mt-2 list-disc pl-5 text-ink-2">{Object.entries(ls.components as Record<string, string>).map(([k, v]) => <li key={k}><span className="font-mono text-xs">{k}</span>: {v}</li>)}</ul>
        <p className="mt-2 text-xs text-warn">{String(ls.k_note)}</p>
      </Section>
      <Section title="Exclusion rule (amendment A1)">
        <p>{ex.description}</p>
        <table className="mt-2 w-full text-sm"><thead><tr className="label text-left"><th>#</th><th>league</th><th className="text-right">score</th><th>basis</th><th>confidence</th><th>excluded</th></tr></thead>
          <tbody>{ex.full_ranking.map((r, i) => <tr key={r.name} className="border-b border-border/40"><td className="py-1 tabular">{i + 1}</td><td>{r.name}</td><td className="text-right tabular">{r.score.toFixed(3)}</td><td className="text-xs text-muted">{r.basis}</td><td>{r.confidence}</td><td>{i < ex.excluded.length ? "yes" : ""}</td></tr>)}</tbody></table>
      </Section>
      <Section title="Percentiles">
        <p>Pool hierarchy (first level with ≥ {String(pct.min_pool_size)} members is used): {(pct.pool_hierarchy as string[]).join(" → ")}</p>
        <p className="text-xs text-muted">membership minutes: {JSON.stringify(pct.pool_min_minutes)}</p>
      </Section>
      <Section title="Transfer value model"><p>Status: <b>{tv.status}</b>. {tv.note}</p></Section>
      <Section title="Limitations"><ul className="list-disc pl-5">{(info.limitations as string[]).map((p) => <li key={p}>{p}</li>)}</ul></Section>
      <p className="text-xs text-muted">metric definitions v{String(info.metric_definition_version)} · config {String(info.config_version)}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card p-5 text-sm"><h2 className="mb-2 font-semibold">{title}</h2>{children}</section>;
}
