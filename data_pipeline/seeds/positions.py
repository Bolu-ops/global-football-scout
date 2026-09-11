"""StatsBomb position_id → canonical position (methodology_spec.md §3.2). Keyed by id,
never by display string (id 23 appears as both 'Center Forward' and 'Striker')."""

from gfs_core.db.models import PositionCode as P
from gfs_core.db.models import PositionGroup as G

# (source_position_id, source name, canonical, group, side, role_variant)
STATSBOMB_POSITIONS: list[tuple[int, str, P, G, str, str | None]] = [
    (1, "Goalkeeper", P.GK, G.GK, "C", None),
    (2, "Right Back", P.RB, G.FB, "R", None),
    (3, "Right Center Back", P.CB, G.CB, "R", None),
    (4, "Center Back", P.CB, G.CB, "C", None),
    (5, "Left Center Back", P.CB, G.CB, "L", None),
    (6, "Left Back", P.LB, G.FB, "L", None),
    (7, "Right Wing Back", P.RWB, G.FB, "R", None),
    (8, "Left Wing Back", P.LWB, G.FB, "L", None),
    (9, "Right Defensive Midfield", P.DM, G.CM, "R", None),
    (10, "Center Defensive Midfield", P.DM, G.CM, "C", None),
    (11, "Left Defensive Midfield", P.DM, G.CM, "L", None),
    (12, "Right Midfield", P.RW, G.AMW, "R", "wide_mid"),
    (13, "Right Center Midfield", P.CM, G.CM, "R", None),
    (14, "Center Midfield", P.CM, G.CM, "C", None),
    (15, "Left Center Midfield", P.CM, G.CM, "L", None),
    (16, "Left Midfield", P.LW, G.AMW, "L", "wide_mid"),
    (17, "Right Wing", P.RW, G.AMW, "R", None),
    (18, "Right Attacking Midfield", P.AM, G.AMW, "R", None),
    (19, "Center Attacking Midfield", P.AM, G.AMW, "C", None),
    (20, "Left Attacking Midfield", P.AM, G.AMW, "L", None),
    (21, "Left Wing", P.LW, G.AMW, "L", None),
    (22, "Right Center Forward", P.ST, G.ST, "R", None),
    (23, "Center Forward", P.ST, G.ST, "C", None),
    (24, "Left Center Forward", P.ST, G.ST, "L", None),
    (25, "Secondary Striker", P.SS, G.AMW, "C", None),
]

POSITION_GROUP_OF: dict[P, G] = {
    P.GK: G.GK,
    P.CB: G.CB,
    P.LB: G.FB,
    P.RB: G.FB,
    P.LWB: G.FB,
    P.RWB: G.FB,
    P.DM: G.CM,
    P.CM: G.CM,
    P.AM: G.AMW,
    P.LW: G.AMW,
    P.RW: G.AMW,
    P.SS: G.AMW,
    P.ST: G.ST,
}
