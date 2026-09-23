"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PlayerSearch } from "@/components/PlayerSearch";
import { ResultsTable } from "@/components/ResultsTable";
import { WhyMatch } from "@/components/Charts";
import { api, fmt, type PlayerSummary, type SimilarityHit, type SimilarityResponse } from "@/lib/api";

export default function ScoutPage() {
  const [target, setTarget] = useState<PlayerSummary | null>(null);
  const [minMinutes, setMinMinutes] = useState(900);
  const [mode, setMode] = useState<"raw" | "adjusted">("raw");
  const [excludeTop, setExcludeTop] = useState(true);
  const [limit, setLimit] = useState(10);
  const [minAge, setMinAge] = useState<string>("");
  const [maxAge, setMaxAge] = useState<string>("");
  const [res, setRes] = useState<SimilarityResponse | null>(null);
  const [selected, setSelected] = useState<SimilarityHit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nl, setNl] = useState("");
  const [nlOut, setNlOut] = useState<{ interpretation: string; notes: string[] } | null>(null);
  // Hidden until the API confirms it: deployments without an LLM key have no natural-language search.
  const [nlEnabled, setNlEnabled] = useState(false);

  useEffect(() => {
    api.features().then((f) => setNlEnabled(f.natural_language)).catch(() => setNlEnabled(false));
  }, []);

  async function analyze(p: PlayerSummary = target!) {
    if (!p) return;
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      const r = await api.similarity(p.player_id, {
        min_minutes: minMinutes, mode, exclude_top_leagues: excludeTop, limit,
        min_age: minAge ? Number(minAge) : null, max_age: maxAge ? Number(maxAge) : null,
      });
      setRes(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function askNl() {
    if (!nl.trim()) return;
    setLoading(true);
    setError(null);
    setNlOut(null);
    try {
      const out = await api.naturalLanguage(nl.trim());
      setNlOut({ interpretation: out.interpretation, notes: out.notes });
      if (out.result) {
        setRes(out.result);
        setSelected(null);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Find statistically similar players</h1>
        <p className="max-w-3xl text-sm text-ink-2">
          Pick a target player. The engine compares per-90 profiles within the same position group and returns the
          closest matches from outside the strongest leagues, with a positional-compatibility factor, a confidence
          level and a metric-by-metric explanation. No language model is involved in the ranking.
        </p>
        <PlayerSearch autoFocus onSelect={(p) => { setTarget(p); analyze(p); }} />
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <label className="flex flex-col gap-1">
            <span className="label">min minutes</span>
            <input type="number" min={90} step={90} value={minMinutes} onChange={(e) => setMinMinutes(Number(e.target.value))} className="w-28 rounded border border-border bg-surface px-2 py-1.5" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">results</span>
            <input type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="w-20 rounded border border-border bg-surface px-2 py-1.5" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">age (at season)</span>
            <div className="flex gap-1">
              <input type="number" min={14} max={50} placeholder="min" value={minAge} onChange={(e) => setMinAge(e.target.value)} className="w-16 rounded border border-border bg-surface px-2 py-1.5" />
              <input type="number" min={14} max={50} placeholder="max" value={maxAge} onChange={(e) => setMaxAge(e.target.value)} className="w-16 rounded border border-border bg-surface px-2 py-1.5" />
            </div>
          </label>
          <label className="flex flex-col gap-1">
            <span className="label">profile mode</span>
            <select value={mode} onChange={(e) => setMode(e.target.value as "raw" | "adjusted")} className="rounded border border-border bg-surface px-2 py-1.5">
              <option value="raw">raw per-90</option>
              <option value="adjusted">league-adjusted (modelled)</option>
            </select>
          </label>
          <label className="flex items-center gap-2 pb-2">
            <input type="checkbox" checked={excludeTop} onChange={(e) => setExcludeTop(e.target.checked)} />
            <span>exclude top-3 leagues from results</span>
          </label>
          <button onClick={() => analyze()} disabled={!target || loading} className="rounded bg-accent px-4 py-2 font-medium text-white disabled:opacity-40">
            {loading ? "Analysing…" : "Analyse"}
          </button>
        </div>
        {nlEnabled && <div className="flex gap-2">
          <input value={nl} onChange={(e) => setNl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && askNl()} placeholder='Or ask: "find me a winger like Vinícius outside the top leagues"' className="w-full rounded border border-border bg-surface px-3 py-2 text-sm placeholder:text-muted" />
          <button onClick={askNl} disabled={loading} className="rounded border border-border px-3 py-2 text-sm hover:bg-surface-2">Ask</button>
        </div>}
        {nlOut && (
          <div className="card p-3 text-sm">
            <div><span className="label">interpreted as</span> <span className="ml-2">{nlOut.interpretation}</span></div>
            {nlOut.notes.map((n, i) => <div key={i} className="mt-1 text-xs text-warn">{n}</div>)}
          </div>
        )}
        {error && <div className="rounded border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{error}</div>}
      </section>

      {res && res.target === null && <div className="card p-4 text-sm text-warn">{res.reason}</div>}

      {res?.target && (
        <section className="space-y-4">
          <div className="card grid gap-3 p-4 md:grid-cols-[1fr_auto]">
            <div>
              <div className="label">target</div>
              <div className="text-lg font-medium">
                <Link href={`/players/${res.target.player_id}?season=${res.target.season_id}`} className="hover:text-accent">{target?.display_name ?? `player ${res.target.player_id}`}</Link>
                <span className="ml-3 font-mono text-sm text-ink-2">{res.target.position_code}{res.target.secondary_position ? ` / ${res.target.secondary_position}` : ""}</span>
              </div>
              <div className="text-sm text-ink-2">{res.target.competition} {res.target.season} · {fmt.int(res.target.minutes)} min · profile mode: {res.target.mode}</div>
            </div>
            <div className="text-right text-xs text-muted">
              <div>{res.candidates_considered} candidates considered</div>
              <div>excluded: {res.excluded_competitions.length ? res.excluded_competitions.map((e) => e.name ?? e.competition_id).join(", ") : "none"}</div>
            </div>
          </div>

          <div className="card p-4">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-base font-semibold">Top {res.results.length} statistical matches</h2>
              <span className="text-xs text-muted">
                click a row for the explanation · click a name for the full profile ·{" "}
                <Link href={`/compare?ids=${[res.target.player_id, ...res.results.slice(0, 4).map((h) => h.player_id)].join(",")}`} className="text-accent">compare top 4</Link>
              </span>
            </div>
            {res.results.length === 0 ? (
              <p className="text-sm text-muted">No eligible candidates with these filters (try a lower minimum minutes; tournament players rarely exceed 600).</p>
            ) : (
              <ResultsTable results={res.results} targetId={res.target.player_id} targetSeasonId={res.target.season_id} onSelect={setSelected} selected={selected?.player_id ?? null} />
            )}
          </div>

          {selected && (
            <div className="card p-4">
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-base font-semibold">Why {selected.display_name} matches — {selected.similarity.toFixed(1)}%</h2>
                <span className="text-xs text-muted">
                  statistical {selected.similarity_statistical.toFixed(1)} × compatibility {selected.compatibility.toFixed(2)} ({selected.compatibility_basis}) · usable features {(selected.usable_weight * 100).toFixed(0)}% · confidence {selected.confidence} ({selected.confidence_score.toFixed(2)})
                </span>
              </div>
              <WhyMatch supporting={selected.explanation.supporting} divergent={selected.explanation.divergent} categories={selected.explanation.category_contributions} labels={[target?.display_name ?? "target", selected.display_name]} />
              <div className="mt-3 text-xs text-muted">
                League context: {selected.competition} {selected.season} — strength {selected.league_strength == null ? "no league score (tournament or no measured input)" : `${selected.league_strength.toFixed(2)} (${selected.league_confidence})`}.
                Estimated transfer value: {fmt.eur(selected.estimated_value_eur)} — {selected.value_note}.
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
