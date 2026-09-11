"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { API_URL, type SeasonRef } from "@/lib/api";

type CompareRow = { code: string; name: string; family: string; is_rate: boolean; values: (number | null)[]; percentiles: (number | null)[] };
type CompareOut = { players: { player_id: number; season: SeasonRef }[]; similarity_to_target: Record<string, number | null>; rows: CompareRow[]; note: string };

function CompareInner() {
  const sp = useSearchParams();
  const ids = (sp.get("ids") ?? "").split(",").map((s) => Number(s)).filter((n) => n > 0).slice(0, 5);
  const [data, setData] = useState<CompareOut | null>(null);
  const [names, setNames] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ids.length < 2) return;
    fetch(`${API_URL}/scouting/compare`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ player_ids: ids }) })
      .then(async (r) => { if (!r.ok) throw new Error(await r.text()); return r.json(); })
      .then(setData)
      .catch((e) => setError(String(e)));
    Promise.all(ids.map((id) => fetch(`${API_URL}/players/${id}`).then((r) => r.json())))
      .then((ps) => setNames(Object.fromEntries(ps.map((p) => [p.player_id, p.display_name]))))
      .catch(() => null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp.get("ids")]);

  if (ids.length < 2) return <p className="text-muted">Add <code>?ids=target,p2,p3</code> (2–5 player ids) to compare.</p>;
  if (error) return <p className="text-bad">{error}</p>;
  if (!data) return <p className="text-muted">Loading…</p>;

  const families = ["attacking", "passing", "possession", "defending", "duels", "goalkeeping"];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Player comparison</h1>
      <div className="card overflow-x-auto p-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="label text-left">
              <th className="py-2">metric</th>
              {data.players.map((p, i) => (
                <th key={p.player_id} className="py-2 pl-4 text-right">
                  <Link href={`/players/${p.player_id}?season=${p.season.season_id}`} className="hover:text-accent">{names[p.player_id] ?? `#${p.player_id}`}</Link>
                  <div className="font-normal normal-case tracking-normal text-muted">{p.season.position ?? "?"} · {p.season.competition} {p.season.name} · {Math.round(p.season.minutes)} min</div>
                  {i > 0 && <div className="font-normal normal-case tracking-normal text-accent">similarity {data.similarity_to_target[String(p.player_id)]?.toFixed(1) ?? "—"}</div>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {families.map((fam) => {
              const rows = data.rows.filter((r) => r.family === fam);
              if (!rows.length) return null;
              return [
                <tr key={`h-${fam}`}><td colSpan={data.players.length + 1} className="label pt-4">{fam}</td></tr>,
                ...rows.map((r) => (
                  <tr key={r.code} className="border-b border-border/40">
                    <td className="py-1 text-ink-2">{r.name}</td>
                    {r.values.map((v, i) => (
                      <td key={i} className="py-1 pl-4 text-right tabular">
                        {v == null ? "—" : r.is_rate ? `${v.toFixed(1)}%` : v.toFixed(2)}
                        <span className="ml-2 text-xs text-muted">{r.percentiles[i] == null ? "" : `${Math.round(r.percentiles[i]!)}th`}</span>
                      </td>
                    ))}
                  </tr>
                )),
              ];
            })}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-muted">{data.note}. Percentiles are each player&apos;s own pool (position group, season window, band).</p>
      </div>
    </div>
  );
}

export default function ComparePage() {
  return <Suspense fallback={<p className="text-muted">Loading…</p>}><CompareInner /></Suspense>;
}
