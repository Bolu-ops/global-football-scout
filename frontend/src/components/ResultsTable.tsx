"use client";

import Link from "next/link";
import { fmt, type SimilarityHit } from "@/lib/api";

const CONF: Record<string, string> = { high: "text-good", medium: "text-warn", low: "text-bad", insufficient: "text-muted" };

export function SimilarityBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <span className="tabular font-medium">{value.toFixed(1)}</span>
    </div>
  );
}

export function ResultsTable({
  results,
  targetId,
  targetSeasonId,
  onSelect,
  selected,
}: {
  results: SimilarityHit[];
  targetId: number;
  targetSeasonId: number;
  onSelect?: (h: SimilarityHit) => void;
  selected?: number | null;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="label border-b border-border text-left">
            <th className="py-2 pr-3">#</th>
            <th className="py-2 pr-3">Player</th>
            <th className="py-2 pr-3">Pos</th>
            <th className="py-2 pr-3">Club · competition</th>
            <th className="py-2 pr-3 text-right">Min</th>
            <th className="py-2 pr-3">Similarity</th>
            <th className="py-2 pr-3 text-right">Compat.</th>
            <th className="py-2 pr-3">Est. value</th>
            <th className="py-2 pr-3">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {results.map((h) => (
            <tr
              key={`${h.player_id}-${h.season_id}`}
              onClick={() => onSelect?.(h)}
              className={`cursor-pointer border-b border-border/60 hover:bg-surface-2 ${selected === h.player_id ? "bg-surface-2" : ""}`}
            >
              <td className="py-2.5 pr-3 tabular text-muted">{h.rank}</td>
              <td className="py-2.5 pr-3">
                <Link
                  href={`/players/${h.player_id}?season=${h.season_id}&target=${targetId}&target_season=${targetSeasonId}`}
                  className="font-medium hover:text-accent"
                  onClick={(e) => e.stopPropagation()}
                >
                  {h.display_name}
                </Link>
                <span className="ml-2 text-xs text-muted">{h.nationality ?? ""}</span>
              </td>
              <td className="py-2.5 pr-3 font-mono text-xs">{h.position}</td>
              <td className="py-2.5 pr-3 text-ink-2">
                {h.team_name ?? "—"} <span className="text-muted">· {h.competition} {h.season}</span>
              </td>
              <td className="py-2.5 pr-3 tabular text-right">{fmt.int(h.minutes)}</td>
              <td className="py-2.5 pr-3"><SimilarityBar value={h.similarity} /></td>
              <td className="py-2.5 pr-3 tabular text-right text-ink-2">{h.compatibility.toFixed(2)}</td>
              <td className="py-2.5 pr-3 text-muted" title={h.value_note}>{fmt.eur(h.estimated_value_eur)}</td>
              <td className={`py-2.5 pr-3 capitalize ${CONF[h.confidence] ?? ""}`}>{h.confidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
