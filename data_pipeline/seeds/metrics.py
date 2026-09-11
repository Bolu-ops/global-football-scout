"""House metric definitions computed from event data (docs/research/statsbomb_open_data.md §3,
docs/research/methodology_spec.md §4.2). `code == canonical_code` for these; provider
aggregates with different definitions get their own prefixed codes."""

from dataclasses import dataclass

from gfs_core.db.models import MetricDirection as D
from gfs_core.db.models import MetricFamily as F
from gfs_core.db.models import MetricScope as S

DEFINITION_VERSION = 1

PITCH_NOTE = "Pitch 120x80 yards; goal centre (120,40); box x>=102 & 18<=y<=62; final third x>=80."


@dataclass(frozen=True)
class MetricSpec:
    code: str
    name: str
    family: F
    rule: str
    scope: S = S.outfield
    direction: D = D.higher_better
    unit: str = "count"
    is_rate: bool = False
    per90_eligible: bool = True


HB, LB, N = D.higher_better, D.lower_better, D.neutral

METRICS: list[MetricSpec] = [
    # --- playing time (from lineups; not per-90) ---
    MetricSpec(
        "minutes",
        "Minutes played (regulation clock)",
        F.playing_time,
        "Sum of lineup position segments on the regulation clock; shootout period excluded.",
        S.all,
        N,
        "minutes",
        per90_eligible=False,
    ),
    MetricSpec(
        "minutes_elapsed",
        "Minutes played incl. stoppage",
        F.playing_time,
        "Sum of lineup position segments using actual Half End timestamps.",
        S.all,
        N,
        "minutes",
        per90_eligible=False,
    ),
    MetricSpec(
        "appearances",
        "Appearances",
        F.playing_time,
        "Matches with minutes > 0.",
        S.all,
        N,
        per90_eligible=False,
    ),
    MetricSpec(
        "starts",
        "Starts",
        F.playing_time,
        "Matches with a segment start_reason = Starting XI.",
        S.all,
        N,
        per90_eligible=False,
    ),
    # --- attacking ---
    MetricSpec(
        "goals", "Goals", F.attacking, "Shot events with outcome Goal (own goals excluded)."
    ),
    MetricSpec(
        "np_goals", "Non-penalty goals", F.attacking, "Goals excluding shot.type = Penalty."
    ),
    MetricSpec("assists", "Assists", F.attacking, "Pass events with pass.goal_assist = true."),
    MetricSpec("xg", "Expected goals (xG)", F.attacking, "Sum of shot.statsbomb_xg.", unit="xg"),
    MetricSpec(
        "npxg",
        "Non-penalty xG",
        F.attacking,
        "Sum of shot.statsbomb_xg excluding penalties.",
        unit="xg",
    ),
    MetricSpec(
        "xa",
        "Expected assists (xA)",
        F.attacking,
        "Sum of statsbomb_xg of the shot whose key_pass_id is the pass (pass.assisted_shot_id).",
        unit="xg",
    ),
    MetricSpec("shots", "Shots", F.attacking, "Shot events (shootout period excluded)."),
    MetricSpec(
        "np_shots", "Non-penalty shots", F.attacking, "Shots excluding shot.type = Penalty."
    ),
    MetricSpec(
        "shots_on_target",
        "Shots on target",
        F.attacking,
        "Shots with outcome in {Goal, Saved, Saved To Post, Saved Off Target}.",
    ),
    MetricSpec(
        "sca",
        "Shot-creating actions",
        F.attacking,
        "Completed pass, completed take-on, foul won or shot that is one of the last two such "
        "team actions in the same possession before a shot (FBref-style; the shooter can be "
        "credited for a preceding take-on/foul won).",
    ),
    MetricSpec(
        "gca", "Goal-creating actions", F.attacking, "SCA restricted to shots with outcome Goal."
    ),
    MetricSpec(
        "touches_att_box",
        "Touches in attacking penalty area",
        F.attacking,
        "Pass, Carry, Shot, Dribble, Miscontrol and COMPLETE Ball Receipt* events whose start "
        "location is in the box (incomplete receipts are not touches).",
    ),
    MetricSpec(
        "penalties_taken", "Penalties taken", F.attacking, "Shots with shot.type = Penalty."
    ),
    MetricSpec(
        "penalties_scored", "Penalties scored", F.attacking, "Penalty shots with outcome Goal."
    ),
    # --- passing ---
    MetricSpec("passes", "Passes attempted", F.passing, "Pass events (all types)."),
    MetricSpec(
        "passes_completed", "Passes completed", F.passing, "Pass events with no pass.outcome."
    ),
    MetricSpec(
        "pass_completion_pct",
        "Pass completion %",
        F.passing,
        "passes_completed / passes * 100.",
        unit="pct",
        is_rate=True,
        per90_eligible=False,
    ),
    MetricSpec(
        "progressive_passes",
        "Progressive passes",
        F.passing,
        "Completed open-play pass (type not in Corner/Free Kick/Throw-in/Goal Kick/Kick Off) "
        "reducing distance to goal centre by >= 10 yards with start_x >= 48, or ending in the box "
        "from outside. " + PITCH_NOTE,
    ),
    MetricSpec(
        "key_passes", "Key passes", F.passing, "Pass events with pass.shot_assist or goal_assist."
    ),
    MetricSpec(
        "passes_final_third",
        "Passes into final third",
        F.passing,
        "Completed pass starting at x < 80 and ending at x >= 80.",
    ),
    MetricSpec(
        "passes_into_box",
        "Passes into penalty area",
        F.passing,
        "Completed pass starting outside and ending inside the box.",
    ),
    MetricSpec(
        "through_balls",
        "Through balls",
        F.passing,
        "pass.through_ball = true or pass.technique = Through Ball.",
    ),
    MetricSpec("crosses", "Crosses", F.passing, "pass.cross = true."),
    MetricSpec("switches", "Switches of play", F.passing, "pass.switch = true."),
    MetricSpec(
        "long_passes",
        "Long passes attempted",
        F.passing,
        "Pass events with pass.length >= 30 yards.",
    ),
    MetricSpec(
        "long_passes_completed", "Long passes completed", F.passing, "Long passes with no outcome."
    ),
    MetricSpec(
        "progressive_pass_distance",
        "Progressive passing distance",
        F.passing,
        "Sum over completed passes of max(0, dist_to_goal(start) - dist_to_goal(end)).",
        unit="yards",
    ),
    # --- possession ---
    MetricSpec(
        "touches",
        "Touches",
        F.possession,
        "Pass, Carry, Shot, Dribble, complete Ball Receipt*, Miscontrol, Ball Recovery, Clearance, "
        "Interception, Block, Foul Won events by the player.",
    ),
    MetricSpec("carries", "Carries", F.possession, "Carry events."),
    MetricSpec(
        "progressive_carries",
        "Progressive carries",
        F.possession,
        "Carry reducing distance to goal centre by >= 10 yards with start_x >= 48, or ending "
        "in the box from outside (same geometry as progressive passes). " + PITCH_NOTE,
    ),
    MetricSpec(
        "carries_final_third",
        "Carries into final third",
        F.possession,
        "Carry starting at x < 80 and ending at x >= 80.",
    ),
    MetricSpec(
        "carries_into_box",
        "Carries into penalty area",
        F.possession,
        "Carry starting outside and ending inside the box.",
    ),
    MetricSpec(
        "carry_distance",
        "Carry distance",
        F.possession,
        "Sum of euclidean carry lengths.",
        unit="yards",
    ),
    MetricSpec(
        "progressive_carry_distance",
        "Progressive carry distance",
        F.possession,
        "Sum over carries of max(0, dist_to_goal(start) - dist_to_goal(end)).",
        unit="yards",
    ),
    MetricSpec("take_ons", "Take-ons attempted", F.possession, "Dribble events."),
    MetricSpec(
        "take_ons_won", "Successful take-ons", F.possession, "Dribble events with outcome Complete."
    ),
    MetricSpec(
        "take_on_success_pct",
        "Take-on success %",
        F.possession,
        "take_ons_won / take_ons * 100.",
        unit="pct",
        is_rate=True,
        per90_eligible=False,
    ),
    MetricSpec("miscontrols", "Miscontrols", F.possession, "Miscontrol events.", direction=LB),
    MetricSpec("dispossessed", "Dispossessed", F.possession, "Dispossessed events.", direction=LB),
    # --- defending ---
    MetricSpec("tackles", "Tackles", F.defending, "Duel events with duel.type = Tackle."),
    MetricSpec(
        "tackles_won",
        "Tackles won",
        F.defending,
        "Tackle duels with outcome in {Won, Success, Success In Play, Success Out}.",
    ),
    MetricSpec("interceptions", "Interceptions", F.defending, "Interception events (any outcome)."),
    MetricSpec(
        "interceptions_won",
        "Interceptions won",
        F.defending,
        "Interception events with outcome in {Won, Success In Play, Success Out}.",
    ),
    MetricSpec("blocks", "Blocks", F.defending, "Block events."),
    MetricSpec("clearances", "Clearances", F.defending, "Clearance events."),
    MetricSpec(
        "ball_recoveries",
        "Ball recoveries",
        F.defending,
        "Ball Recovery events without recovery_failure.",
    ),
    MetricSpec("pressures", "Pressures", F.defending, "Pressure events."),
    MetricSpec(
        "counterpressures",
        "Counterpressures",
        F.defending,
        "Pressure events with counterpress = true.",
    ),
    MetricSpec(
        "successful_pressures",
        "Successful pressures",
        F.defending,
        "Pressures after which the pressing team has possession within 5 seconds "
        "(possession_team changes to the presser's team). Approximation, documented.",
    ),
    MetricSpec(
        "pressure_success_pct",
        "Pressure success %",
        F.defending,
        "successful_pressures / pressures * 100.",
        unit="pct",
        is_rate=True,
        per90_eligible=False,
    ),
    MetricSpec(
        "defensive_actions",
        "Defensive actions",
        F.defending,
        "tackles + interceptions + blocks + clearances.",
    ),
    MetricSpec(
        "dribbled_past", "Dribbled past", F.defending, "Dribbled Past events.", direction=LB
    ),
    MetricSpec(
        "fouls_committed", "Fouls committed", F.defending, "Foul Committed events.", direction=LB
    ),
    MetricSpec("fouls_won", "Fouls won", F.defending, "Foul Won events."),
    MetricSpec("errors", "Errors", F.defending, "Error events.", direction=LB),
    # --- duels ---
    MetricSpec(
        "ground_duels",
        "Ground duels",
        F.duels,
        "Tackle duels + Dribble (as attacker) + Dribbled Past (as defender) + 50/50 events. "
        "Approximation of provider 'ground duels'.",
    ),
    MetricSpec(
        "ground_duels_won",
        "Ground duels won",
        F.duels,
        "tackles_won + take_ons_won + 50/50 with outcome in {Won, Success To Team}.",
    ),
    MetricSpec(
        "aerial_duels",
        "Aerial duels",
        F.duels,
        "Duel type Aerial Lost + events (Pass, Shot, Clearance, Miscontrol) with aerial_won = true.",
    ),
    MetricSpec("aerial_duels_won", "Aerial duels won", F.duels, "Events with aerial_won = true."),
    MetricSpec(
        "aerial_duel_win_pct",
        "Aerial duel win %",
        F.duels,
        "aerial_duels_won / aerial_duels * 100.",
        unit="pct",
        is_rate=True,
        per90_eligible=False,
    ),
    # --- discipline ---
    MetricSpec(
        "yellow_cards",
        "Yellow cards",
        F.discipline,
        "Lineup cards Yellow Card (+ Second Yellow).",
        S.all,
        LB,
    ),
    MetricSpec(
        "red_cards", "Red cards", F.discipline, "Lineup cards Red Card or Second Yellow.", S.all, LB
    ),
    # --- goalkeeping ---
    MetricSpec(
        "gk_shots_faced",
        "Shots faced",
        F.goalkeeping,
        "Goal Keeper events with type in {Shot Faced, Shot Saved, Goal Conceded, Penalty Saved, "
        "Penalty Conceded}.",
        S.goalkeeper,
        N,
    ),
    MetricSpec(
        "gk_saves",
        "Saves",
        F.goalkeeping,
        "Goal Keeper type in {Shot Saved, Penalty Saved}.",
        S.goalkeeper,
    ),
    MetricSpec(
        "gk_goals_conceded",
        "Goals conceded",
        F.goalkeeping,
        "Goal Keeper type Goal Conceded, plus Penalty Conceded with outcome not a save.",
        S.goalkeeper,
        LB,
    ),
    MetricSpec(
        "gk_save_pct",
        "Save %",
        F.goalkeeping,
        "gk_saves / (gk_saves + gk_goals_conceded) * 100.",
        S.goalkeeper,
        HB,
        "pct",
        is_rate=True,
        per90_eligible=False,
    ),
    MetricSpec(
        "gk_psxg",
        "Post-shot xG faced",
        F.goalkeeping,
        "NOT AVAILABLE in StatsBomb open data (no post-shot xG field); reserved for providers "
        "that supply it. Never imputed.",
        S.goalkeeper,
        N,
        "xg",
    ),
    MetricSpec(
        "gk_penalties_faced",
        "Penalties faced",
        F.goalkeeping,
        "Goal Keeper type in {Penalty Saved, Penalty Conceded}.",
        S.goalkeeper,
        N,
    ),
    MetricSpec(
        "gk_penalties_saved",
        "Penalties saved",
        F.goalkeeping,
        "Goal Keeper type Penalty Saved.",
        S.goalkeeper,
    ),
    MetricSpec(
        "gk_sweeper_actions",
        "Sweeper actions",
        F.goalkeeping,
        "Goal Keeper type Keeper Sweeper.",
        S.goalkeeper,
    ),
    MetricSpec(
        "gk_claims",
        "Cross claims / collections",
        F.goalkeeping,
        "Goal Keeper type in {Collected, Punch}.",
        S.goalkeeper,
    ),
    MetricSpec(
        "gk_passes",
        "GK passes attempted",
        F.goalkeeping,
        "Pass events by the goalkeeper.",
        S.goalkeeper,
        N,
    ),
    MetricSpec(
        "gk_passes_completed",
        "GK passes completed",
        F.goalkeeping,
        "Pass events by the goalkeeper with no outcome.",
        S.goalkeeper,
    ),
    MetricSpec(
        "gk_pass_completion_pct",
        "GK pass completion %",
        F.goalkeeping,
        "gk_passes_completed / gk_passes * 100.",
        S.goalkeeper,
        HB,
        "pct",
        is_rate=True,
        per90_eligible=False,
    ),
    MetricSpec(
        "gk_long_passes",
        "GK long passes",
        F.goalkeeping,
        "GK passes with length >= 30 yards.",
        S.goalkeeper,
        N,
    ),
]

METRIC_BY_CODE = {m.code: m for m in METRICS}
