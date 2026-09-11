"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import type { Contribution, MetricValue } from "@/lib/api";

const SERIES_1 = "#3987e5";
const SERIES_2 = "#d95926";

export const RADAR_METRICS: Record<string, string[]> = {
  GK: ["gk_save_pct", "gk_saves", "gk_sweeper_actions", "gk_claims", "gk_pass_completion_pct", "gk_long_passes"],
  default: [
    "npxg", "np_shots", "xa", "sca", "touches_att_box", "progressive_passes", "progressive_carries",
    "take_ons_won", "pressures", "tackles", "interceptions", "aerial_duels_won",
  ],
};

export function PercentileRadar({
  metrics,
  group,
  compare,
  labels,
}: {
  metrics: MetricValue[];
  group: string | null;
  compare?: MetricValue[];
  labels?: [string, string];
}) {
  const codes = RADAR_METRICS[group === "GK" ? "GK" : "default"];
  const byCode = Object.fromEntries(metrics.map((m) => [m.code, m]));
  const cmp = compare ? Object.fromEntries(compare.map((m) => [m.code, m])) : null;
  const data = codes
    .filter((c) => byCode[c])
    .map((c) => ({
      metric: byCode[c].name.replace("Non-penalty ", "np").replace("Expected ", ""),
      a: byCode[c].percentile ?? 0,
      b: cmp?.[c]?.percentile ?? 0,
      missingA: byCode[c].percentile == null,
      missingB: cmp ? cmp[c]?.percentile == null : false,
    }));
  const anyMissing = data.some((d) => d.missingA || d.missingB);
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="#2f312e" />
          <PolarAngleAxis dataKey="metric" tick={{ fill: "#c3c2b7", fontSize: 11 }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar name={labels?.[0] ?? "percentile"} dataKey="a" stroke={SERIES_1} fill={SERIES_1} fillOpacity={0.18} strokeWidth={2} />
          {cmp && <Radar name={labels?.[1] ?? "comparison"} dataKey="b" stroke={SERIES_2} fill={SERIES_2} fillOpacity={0.14} strokeWidth={2} />}
          {cmp && <Legend wrapperStyle={{ fontSize: 12, color: "#c3c2b7" }} />}
          <Tooltip
            contentStyle={{ background: "#232422", border: "1px solid #2f312e", fontSize: 12 }}
            formatter={(v) => [`${Math.round(Number(v))}th`, "percentile"]}
          />
        </RadarChart>
      </ResponsiveContainer>
      {anyMissing && <p className="mt-1 text-xs text-muted">Metrics without a percentile pool are drawn at 0 and marked “—” in the table.</p>}
    </div>
  );
}

export function PercentileBars({ metrics }: { metrics: MetricValue[] }) {
  const families = ["attacking", "passing", "possession", "defending", "duels", "discipline", "goalkeeping"];
  return (
    <div className="space-y-5">
      {families.map((fam) => {
        const rows = metrics.filter((m) => m.family === fam);
        if (!rows.length) return null;
        return (
          <div key={fam}>
            <div className="label mb-2">{fam}</div>
            <table className="w-full text-sm">
              <tbody>
                {rows.map((m) => (
                  <tr key={m.code} className="border-b border-border/40" title={m.definition ?? ""}>
                    <td className="w-64 py-1 pr-2 text-ink-2">{m.name}</td>
                    <td className="w-20 py-1 pr-2 text-right tabular">{m.is_rate ? `${m.value?.toFixed(1)}%` : m.per90?.toFixed(2) ?? "—"}</td>
                    <td className="w-14 py-1 pr-2 text-xs text-muted">{m.is_rate ? "" : "/90"}</td>
                    <td className="py-1">
                      {m.percentile == null ? (
                        <span className="text-xs text-muted">no pool ≥ min size</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-full max-w-64 overflow-hidden rounded-sm bg-surface-2">
                            <div className="h-full bg-accent" style={{ width: `${m.percentile}%` }} />
                          </div>
                          <span className="w-8 tabular text-xs">{Math.round(m.percentile)}</span>
                          <span className="text-xs text-muted" title={m.percentile_pool ?? ""}>n={m.percentile_pool_n}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

export function WhyMatch({ supporting, divergent, categories, labels }: { supporting: Contribution[]; divergent: Contribution[]; categories: Record<string, number>; labels: [string, string] }) {
  const Row = ({ c }: { c: Contribution }) => (
    <tr className="border-b border-border/40">
      <td className="py-1 pr-2 text-ink-2">{c.feature.replaceAll("_", " ")}</td>
      <td className="py-1 pr-2 text-xs text-muted">{c.category}</td>
      <td className="py-1 pr-2 text-right tabular">{c.target_value.toFixed(2)}</td>
      <td className="py-1 pr-2 text-right tabular">{c.candidate_value.toFixed(2)}</td>
      <td className={`py-1 text-right tabular ${Math.abs(c.delta_z) < 0.5 ? "text-good" : "text-warn"}`}>{c.delta_z > 0 ? "+" : ""}{c.delta_z.toFixed(2)}</td>
    </tr>
  );
  return (
    <div className="grid gap-6 md:grid-cols-[1fr_220px]">
      <div>
        <table className="w-full text-sm">
          <thead>
            <tr className="label text-left"><th className="py-1">metric (per 90 / %)</th><th></th><th className="text-right">{labels[0]}</th><th className="text-right">{labels[1]}</th><th className="text-right">Δz</th></tr>
          </thead>
          <tbody>
            <tr><td colSpan={5} className="pt-2 text-xs text-good">strongest similarities</td></tr>
            {supporting.map((c) => <Row key={`s-${c.feature}`} c={c} />)}
            <tr><td colSpan={5} className="pt-3 text-xs text-warn">largest differences</td></tr>
            {divergent.map((c) => <Row key={`d-${c.feature}`} c={c} />)}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-muted">Δz = difference in standardized score within the position pool; values are per-90 unless the metric is a percentage.</p>
      </div>
      <div>
        <div className="label mb-2">category contribution</div>
        {Object.entries(categories).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
          <div key={k} className="mb-1.5 text-sm">
            <div className="flex justify-between"><span className="text-ink-2">{k}</span><span className="tabular text-xs">{v.toFixed(1)}</span></div>
            <div className="h-1.5 w-full overflow-hidden rounded-sm bg-surface-2"><div className="h-full bg-accent" style={{ width: `${Math.min(100, v)}%` }} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}
