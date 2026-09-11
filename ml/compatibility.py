"""Positional compatibility in [0, 1] between canonical positions (methodology_spec.md §7.4).
Symmetric; GK vs any outfield position is 0 (hard rule)."""

from __future__ import annotations

from gfs_core.db.models import PositionCode as P

_PAIRS: dict[frozenset[P], float] = {}


def _set(a: P, b: P, v: float) -> None:
    _PAIRS[frozenset((a, b))] = v


for _p in P:
    _set(_p, _p, 1.0)

# full-backs / wing-backs
_set(P.LB, P.RB, 0.85)
_set(P.LB, P.LWB, 0.9)
_set(P.RB, P.RWB, 0.9)
_set(P.LWB, P.RWB, 0.85)
_set(P.LB, P.RWB, 0.75)
_set(P.RB, P.LWB, 0.75)
_set(P.LB, P.CB, 0.45)
_set(P.RB, P.CB, 0.45)
_set(P.LWB, P.CB, 0.3)
_set(P.RWB, P.CB, 0.3)
_set(P.LWB, P.LW, 0.55)
_set(P.RWB, P.RW, 0.55)
_set(P.LWB, P.RW, 0.45)
_set(P.RWB, P.LW, 0.45)
_set(P.LB, P.LW, 0.35)
_set(P.RB, P.RW, 0.35)
_set(P.LWB, P.CM, 0.35)
_set(P.RWB, P.CM, 0.35)
# central defence / midfield
_set(P.CB, P.DM, 0.5)
_set(P.CB, P.CM, 0.2)
_set(P.DM, P.CM, 0.8)
_set(P.DM, P.AM, 0.4)
_set(P.CM, P.AM, 0.7)
_set(P.LB, P.DM, 0.3)
_set(P.RB, P.DM, 0.3)
_set(P.LB, P.CM, 0.3)
_set(P.RB, P.CM, 0.3)
# attacking midfield / wings / strikers
_set(P.AM, P.LW, 0.7)
_set(P.AM, P.RW, 0.7)
_set(P.AM, P.SS, 0.85)
_set(P.AM, P.ST, 0.45)
_set(P.LW, P.RW, 0.9)
_set(P.LW, P.SS, 0.65)
_set(P.RW, P.SS, 0.65)
_set(P.LW, P.ST, 0.5)
_set(P.RW, P.ST, 0.5)
_set(P.SS, P.ST, 0.8)
_set(P.CM, P.LW, 0.3)
_set(P.CM, P.RW, 0.3)
_set(P.CM, P.SS, 0.35)
_set(P.CM, P.ST, 0.15)
_set(P.DM, P.LW, 0.15)
_set(P.DM, P.RW, 0.15)
_set(P.DM, P.SS, 0.15)
_set(P.DM, P.ST, 0.1)
_set(P.CB, P.ST, 0.05)
_set(P.CB, P.AM, 0.1)
_set(P.CB, P.LW, 0.05)
_set(P.CB, P.RW, 0.05)
_set(P.CB, P.SS, 0.05)


def compatibility(a: P, b: P) -> float:
    if a == P.GK or b == P.GK:
        return 1.0 if a == b else 0.0
    return _PAIRS.get(frozenset((a, b)), 0.1)


def best_compatibility(
    target: tuple[P, P | None], candidate: tuple[P, P | None], secondary_factor: float = 0.9
) -> tuple[float, str]:
    """Max compatibility over primary/secondary combinations; secondary use is discounted."""
    best, how = compatibility(target[0], candidate[0]), f"{target[0].value}-{candidate[0].value}"
    combos = []
    if target[1]:
        combos.append((target[1], candidate[0], secondary_factor))
    if candidate[1]:
        combos.append((target[0], candidate[1], secondary_factor))
    if target[1] and candidate[1]:
        combos.append((target[1], candidate[1], secondary_factor * secondary_factor))
    for a, b, factor in combos:
        v = compatibility(a, b) * factor
        if v > best:
            best, how = v, f"{a.value}-{b.value}"
    return best, how
