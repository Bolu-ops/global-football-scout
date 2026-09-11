"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { PercentileBars, PercentileRadar, WhyMatch } from "@/components/Charts";
import { ResultsTable } from "@/components/ResultsTable";
import { api, fmt, type PlayerDetail, type PlayerStats, type SimilarityHit, type SimilarityResponse, type TransferValue } from "@/lib/api";

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const playerId = Number(id);
  const seasonParam = sp.get("season");
  const targetId = sp.get("target") ? Number(sp.get("target")) : null;
  const targetSeason = sp.get("target_season") ? Number(sp.get("target_season")) : null;

  const [player, setPlayer] = useState<PlayerDetail | null>(null);
  const [stats, setStats] = useState<PlayerStats | null>(null);
  const [seasonId, setSeasonId] = useState<number | undefined>(seasonParam ? Number(seasonParam) : undefined);
  const [value, setValue] = useState<TransferValue | null>(null);
  const [sim, setSim] = useState<SimilarityResponse | null>(null);
  const [targetStats, setTargetStats] = useState<PlayerStats | null>(null);
  const [targetName, setTargetName] = useState<string>("target");
  const [match, setMatch] = useState<SimilarityHit | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.player(playerId).then(setPlayer).catch((e) => setError(String(e)));
    api.transferValue(playerId).then(setValue).catch(() => null);
  }, [playerId]);

  useEffect(() => {
    api.stats(playerId, seasonId).then(setStats).catch((e) => setError(String(e)));
  }, [playerId, seasonId]);

  useEffect(() => {
    if (!stats) return;
    const minMinutes = stats.season.competition_type === "international_national" ? 250 : 900;
    api.similarity(playerId, { season_id: stats.season.season_id, min_minutes: Math.min(minMinutes, Math.max(90, Math.floor(stats.season.minutes))), limit: 10 }).then(setSim).catch(() => null);
  }, [playerId, stats]);

  useEffect(() => {
    if (!targetId || !stats) return;
    api.stats(targetId, targetSeason ?? undefined).then(setTargetStats).catch(() => null);
    api.player(targetId).then((p) => setTargetName(p.display_name)).catch(() => null);
    const minMinutes = Math.max(90, Math.min(250, Math.floor(stats.season.minutes)));
    api.similarity(targetId, { season_id: targetSeason ?? undefined, min_minutes: minMinutes, limit: 50 })
      .then((r) => setMatch(r.results.find((h) => h.player_id === playerId) ?? null))
      .catch(() => null);
  }, [targetId, targetSeason, playerId, stats]);

  if (error) return <div className="text-bad">{error}</div>;
  if (!player || !stats) return <div className="text-muted">Loading…</div>;
  const s = stats.season;

  return (
    <div className="space-y-6">
      <section className="card grid gap-4 p-5 md:grid-cols-[1fr_auto]">
        <div>
          <div className="label">player profile</div>
          <h1 className="text-2xl font-semibold">{player.display_name}</h1>
          <div className="text-sm text-ink-2">
            {player.full_name} · {player.nationality ?? "nationality unavailable"} · {player.gender} ·{" "}
            {player.age != null ? `${player.age} y` : <span title={player.age_note ?? ""}>age: Data unavailable</span>}
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <span className="rounded bg-surface-2 px-2 py-1 font-mono">{s.position ?? "?"} · {s.position_group ?? "?"}</span>
            <span className="rounded bg-surface-2 px-2 py-1">{s.teams.join(" / ")}</span>
            <span className="rounded bg-surface-2 px-2 py-1">{s.competition} {s.name} · {s.coverage_type.replace("_", " ")}</span>
            <span className="rounded bg-surface-2 px-2 py-1 tabular">{fmt.int(s.minutes)} min · {s.appearances} apps · {s.starts} starts</span>
            <span className="rounded bg-surface-2 px-2 py-1">league strength: {s.league_strength == null ? "none (tournament / no measured input)" : `${s.league_strength.toFixed(2)} · ${s.league_strength_confidence}`}</span>
          </div>
        </div>
        <div className="text-sm">
          <div className="label">season</div>
          <select value={s.season_id} onChange={(e) => setSeasonId(Number(e.target.value))} className="rounded border border-border bg-surface px-2 py-1.5">
            {player.seasons.map((x) => (
              <option key={x.season_id} value={x.season_id}>{x.competition} {x.name} · {Math.round(x.minutes)} min</option>
            ))}
          </select>
          <div className="mt-3 text-xs text-muted">
            data: {player.sources.join(", ")} · completeness flags: {player.data_quality.flags.length ? player.data_quality.flags.join(", ") : "none"}
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="card p-5">
          <div className="mb-1 flex items-baseline justify-between">
            <h2 className="font-semibold">Statistical profile</h2>
            <span className="text-xs text-muted">percentiles vs. {s.position_group} pool</span>
          </div>
          <PercentileRadar metrics={stats.metrics} group={s.position_group} compare={targetStats?.metrics} labels={[player.display_name, targetName]} />
        </div>
        <div className="card p-5">
          <h2 className="mb-2 font-semibold">Estimated transfer value</h2>
          <div className="text-3xl font-semibold tabular">{fmt.eur(value?.estimated_value_eur)}</div>
          <div className="mt-1 text-sm text-ink-2">{value?.status}</div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div><div className="label">range</div><div>{value?.range_eur?.[0] != null ? `${fmt.eur(value.range_eur[0])} – ${fmt.eur(value.range_eur[1])}` : "Data unavailable"}</div></div>
            <div><div className="label">confidence</div><div className="capitalize">{value?.confidence ?? "—"}</div></div>
            <div><div className="label">reference market estimate</div><div>{fmt.eur(value?.reference_market_value_eur)}</div></div>
            <div><div className="label">model–market discrepancy</div><div>{fmt.eur(value?.model_market_discrepancy_eur)}</div></div>
          </div>
          <p className="mt-4 text-xs text-muted">The value model is trained only on real historical transfer fees; until a licensed fee source is loaded every value is “Data unavailable”. A reference market estimate, when present, is never used as a model input.</p>
        </div>
      </section>

      {match && (
        <section className="card p-5">
          <h2 className="mb-1 font-semibold">Why this player matches {targetName} — {match.similarity.toFixed(1)}%</h2>
          <div className="mb-3 text-xs text-muted">statistical {match.similarity_statistical.toFixed(1)} × compatibility {match.compatibility.toFixed(2)} ({match.compatibility_basis}) · confidence {match.confidence}</div>
          <WhyMatch supporting={match.explanation.supporting} divergent={match.explanation.divergent} categories={match.explanation.category_contributions} labels={[targetName, player.display_name]} />
        </section>
      )}

      <section className="card p-5">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-semibold">Metrics — {s.competition} {s.name}</h2>
          <span className="text-xs text-muted">source: {stats.metrics[0]?.source} · hover a metric for its definition</span>
        </div>
        <PercentileBars metrics={stats.metrics} />
        <p className="mt-3 text-xs text-muted">{stats.percentile_note}</p>
      </section>

      {sim?.target && (
        <section className="card p-5">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="font-semibold">Players similar to {player.display_name}</h2>
            <span className="text-xs text-muted">excluded: {sim.excluded_competitions.map((e) => e.name ?? e.competition_id).join(", ") || "none"}</span>
          </div>
          {sim.results.length ? (
            <ResultsTable results={sim.results} targetId={playerId} targetSeasonId={s.season_id} />
          ) : (
            <p className="text-sm text-muted">No eligible candidates at the current minutes threshold.</p>
          )}
        </section>
      )}

      <section className="card p-5 text-sm">
        <h2 className="mb-2 font-semibold">Scouting report</h2>
        <ul className="list-disc space-y-1 pl-5 text-ink-2">
          <li><b>Overview:</b> {player.display_name} ({s.position ?? "?"}) — {fmt.int(s.minutes)} minutes across {s.appearances} appearances for {s.teams.join(" / ")} in {s.competition} {s.name}.</li>
          <li><b>Strengths:</b> {topMetrics(stats, true)}</li>
          <li><b>Weaknesses:</b> {topMetrics(stats, false)}</li>
          <li><b>League context:</b> {s.league_strength == null ? "no league-strength score applies (national-team tournament or no measured input); raw percentiles are shown against the tournament pool." : `league strength ${s.league_strength.toFixed(2)} (${s.league_strength_confidence}); adjusted percentiles use k-exponents that are defaults until fitted.`}</li>
          <li><b>Transfer value:</b> {value?.status}</li>
          <li><b>Data sources:</b> {player.sources.join(", ")} — see <Link href="/sources" className="text-accent">licences and attribution</Link>.</li>
          <li><b>Limitations:</b> sample size {s.minutes < 900 ? "is small (< 900 min); treat percentiles with caution" : "is adequate"}; no age/height/foot data loaded; percentiles missing where no pool reaches the minimum size.</li>
        </ul>
      </section>
    </div>
  );
}

function topMetrics(stats: PlayerStats, best: boolean): string {
  const rows = stats.metrics.filter((m) => m.percentile != null && m.family !== "discipline");
  if (!rows.length) return "not enough comparable players for percentiles";
  const sorted = [...rows].sort((a, b) => (best ? b.percentile! - a.percentile! : a.percentile! - b.percentile!)).slice(0, 4);
  return sorted.map((m) => `${m.name} (${Math.round(m.percentile!)}th)`).join(", ");
}
