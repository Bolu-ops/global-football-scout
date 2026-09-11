"use client";

import { useEffect, useRef, useState } from "react";
import { api, type PlayerSummary } from "@/lib/api";

export function PlayerSearch({ onSelect, autoFocus }: { onSelect: (p: PlayerSummary) => void; autoFocus?: boolean }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<PlayerSummary[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 2) return;
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        setHits(await api.searchPlayers(q.trim()));
        setOpen(true);
      } catch {
        setHits([]);
      } finally {
        setLoading(false);
      }
    }, 200);
  }, [q]);

  return (
    <div className="relative">
      <input
        autoFocus={autoFocus}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          if (e.target.value.trim().length < 2) setHits([]);
        }}
        onFocus={() => hits.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search a player — e.g. Vinícius Júnior, Sadio Mané, Alexia Putellas"
        className="w-full rounded-lg border border-border bg-surface px-4 py-3 text-base outline-none placeholder:text-muted focus:border-accent"
      />
      {loading && <span className="absolute right-4 top-3.5 text-xs text-muted">searching…</span>}
      {open && hits.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-xl">
          {hits.map((p) => (
            <li key={p.player_id}>
              <button
                onMouseDown={() => {
                  onSelect(p);
                  setQ(p.display_name);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-surface-2"
              >
                <span>
                  <span className="font-medium">{p.display_name}</span>
                  <span className="ml-2 text-xs text-muted">{p.nationality ?? ""}</span>
                </span>
                <span className="text-xs text-ink-2">
                  {p.latest_season
                    ? `${p.latest_season.position ?? "?"} · ${p.latest_season.teams.join("/")} · ${p.latest_season.competition} ${p.latest_season.name} · ${Math.round(p.latest_season.minutes)} min`
                    : "no minutes loaded"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
