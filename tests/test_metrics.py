import uuid

import pytest

from data_pipeline.ingestion.statsbomb.metrics import compute_match_metrics, dist_to_goal, in_box
from tests.conftest import P_A1, P_A2, P_A3, P_B1, P_B_GK, TEAM_A, TEAM_B, ev


def uid(i: int) -> str:
    return str(uuid.UUID(int=i))


def test_geometry_helpers():
    assert dist_to_goal([120, 40]) == 0
    assert in_box([110, 40]) and not in_box([100, 40]) and not in_box([110, 10])


def test_progressive_pass_rules():
    events = [
        # 12 yards closer to goal from own half start x=50 -> counts
        ev(
            1,
            "Pass",
            TEAM_A,
            P_A1,
            location=[50, 40],
            **{"pass": {"end_location": [62, 40], "length": 12, "recipient": {"id": P_A2}}},
        ),
        # starts in own 40% (x < 48) -> excluded even though it gains 20 yards
        ev(
            2,
            "Pass",
            TEAM_A,
            P_A1,
            location=[20, 40],
            **{"pass": {"end_location": [40, 40], "length": 20}},
        ),
        # into the box from outside -> counts regardless of distance
        ev(
            3,
            "Pass",
            TEAM_A,
            P_A1,
            location=[100, 40],
            **{"pass": {"end_location": [104, 40], "length": 4}},
        ),
        # incomplete -> not progressive, still attempted
        ev(
            4,
            "Pass",
            TEAM_A,
            P_A1,
            location=[50, 40],
            **{"pass": {"end_location": [80, 40], "length": 30, "outcome": {"name": "Incomplete"}}},
        ),
        # set piece (corner) into the box -> excluded from progressive, counts as pass into box
        ev(
            5,
            "Pass",
            TEAM_A,
            P_A1,
            location=[120, 0],
            **{"pass": {"end_location": [110, 40], "length": 41, "type": {"name": "Corner"}}},
        ),
    ]
    m = compute_match_metrics(events)[P_A1]
    assert m["passes"] == 5
    assert m["passes_completed"] == 4
    assert m["progressive_passes"] == 2
    assert m["passes_into_box"] == 2
    assert m["long_passes"] == 2 and m["long_passes_completed"] == 1


def test_xa_key_passes_assists_and_shots():
    shot_id = uid(20)
    events = [
        ev(
            10,
            "Pass",
            TEAM_A,
            P_A1,
            location=[90, 40],
            **{
                "pass": {
                    "end_location": [105, 40],
                    "length": 15,
                    "shot_assist": True,
                    "assisted_shot_id": shot_id,
                }
            },
        ),
        {
            **ev(
                20,
                "Shot",
                TEAM_A,
                P_A2,
                location=[105, 40],
                **{
                    "shot": {
                        "statsbomb_xg": 0.31,
                        "outcome": {"name": "Saved"},
                        "type": {"name": "Open Play"},
                        "key_pass_id": uid(10),
                    }
                },
            ),
            "id": shot_id,
        },
        ev(
            30,
            "Pass",
            TEAM_A,
            P_A1,
            location=[90, 40],
            **{
                "pass": {
                    "end_location": [108, 40],
                    "length": 18,
                    "goal_assist": True,
                    "assisted_shot_id": uid(40),
                }
            },
        ),
        {
            **ev(
                40,
                "Shot",
                TEAM_A,
                P_A2,
                location=[108, 40],
                **{
                    "shot": {
                        "statsbomb_xg": 0.55,
                        "outcome": {"name": "Goal"},
                        "type": {"name": "Open Play"},
                    }
                },
            ),
            "id": uid(40),
        },
        ev(
            50,
            "Shot",
            TEAM_A,
            P_A2,
            location=[108, 40],
            **{
                "shot": {
                    "statsbomb_xg": 0.76,
                    "outcome": {"name": "Goal"},
                    "type": {"name": "Penalty"},
                }
            },
        ),
        ev(
            60,
            "Shot",
            TEAM_A,
            P_A2,
            location=[95, 30],
            **{
                "shot": {
                    "statsbomb_xg": 0.03,
                    "outcome": {"name": "Off T"},
                    "type": {"name": "Open Play"},
                }
            },
        ),
    ]
    m = compute_match_metrics(events)
    a1, a2 = m[P_A1], m[P_A2]
    assert a1["key_passes"] == 2 and a1["assists"] == 1
    assert abs(a1["xa"] - 0.86) < 1e-9
    assert a2["shots"] == 4 and a2["np_shots"] == 3
    assert a2["goals"] == 2 and a2["np_goals"] == 1
    assert a2["shots_on_target"] == 3
    assert abs(a2["xg"] - 1.65) < 1e-9 and abs(a2["npxg"] - 0.89) < 1e-9
    assert a2["penalties_taken"] == 1 and a2["penalties_scored"] == 1


def test_shootout_period_excluded():
    events = [
        ev(
            1,
            "Shot",
            TEAM_A,
            P_A1,
            period=5,
            location=[108, 40],
            **{
                "shot": {
                    "statsbomb_xg": 0.76,
                    "outcome": {"name": "Goal"},
                    "type": {"name": "Penalty"},
                }
            },
        )
    ]
    assert P_A1 not in compute_match_metrics(events)


def test_own_goal_not_a_goal():
    events = [
        ev(1, "Own Goal Against", TEAM_A, P_A1, location=[5, 40]),
        ev(2, "Own Goal For", TEAM_B, P_B1),
    ]
    m = compute_match_metrics(events)
    assert m.get(P_A1, {}).get("goals", 0) == 0
    assert m.get(P_B1, {}).get("goals", 0) == 0


def test_sca_gca_window_and_possession_boundary():
    events = [
        ev(
            1,
            "Pass",
            TEAM_A,
            P_A3,
            possession=1,
            location=[40, 40],
            **{"pass": {"end_location": [60, 40], "length": 20}},
        ),
        ev(
            2,
            "Pass",
            TEAM_A,
            P_A1,
            possession=2,
            location=[60, 40],
            **{"pass": {"end_location": [80, 40], "length": 20}},
        ),
        ev(
            3,
            "Dribble",
            TEAM_A,
            P_A2,
            possession=2,
            location=[80, 40],
            **{"dribble": {"outcome": {"name": "Complete"}}},
        ),
        ev(
            4,
            "Carry",
            TEAM_A,
            P_A2,
            possession=2,
            location=[80, 40],
            **{"carry": {"end_location": [100, 40]}},
        ),
        ev(
            5,
            "Shot",
            TEAM_A,
            P_A2,
            possession=2,
            location=[100, 40],
            **{
                "shot": {
                    "statsbomb_xg": 0.2,
                    "outcome": {"name": "Goal"},
                    "type": {"name": "Open Play"},
                }
            },
        ),
    ]
    m = compute_match_metrics(events)
    assert m[P_A2]["sca"] == 1 and m[P_A2]["gca"] == 1  # own take-on credited
    assert m[P_A1]["sca"] == 1 and m[P_A1]["gca"] == 1
    assert m[P_A3].get("sca", 0) == 0  # different possession


def test_pressure_success_window():
    events = [
        ev(
            1,
            "Pressure",
            TEAM_A,
            P_A1,
            ts="00:10:00.000",
            possession=4,
            possession_team=TEAM_B,
            location=[60, 40],
        ),
        ev(
            2,
            "Ball Recovery",
            TEAM_A,
            P_A2,
            ts="00:10:03.000",
            possession=5,
            possession_team=TEAM_A,
            location=[60, 40],
        ),
        ev(
            3,
            "Pressure",
            TEAM_A,
            P_A1,
            ts="00:20:00.000",
            possession=6,
            possession_team=TEAM_B,
            location=[60, 40],
        ),
        ev(
            4,
            "Pass",
            TEAM_B,
            P_B1,
            ts="00:20:04.000",
            possession=6,
            possession_team=TEAM_B,
            location=[60, 40],
            **{"pass": {"end_location": [50, 40], "length": 10}},
        ),
        ev(
            5,
            "Ball Recovery",
            TEAM_A,
            P_A2,
            ts="00:20:09.000",
            possession=7,
            possession_team=TEAM_A,
            location=[60, 40],
        ),
    ]
    m = compute_match_metrics(events)[P_A1]
    assert m["pressures"] == 2
    assert m["successful_pressures"] == 1  # second recovery is 9 s later -> not credited


def test_duels_and_defensive_actions():
    events = [
        ev(
            1,
            "Duel",
            TEAM_A,
            P_A1,
            location=[30, 40],
            **{"duel": {"type": {"name": "Tackle"}, "outcome": {"name": "Won"}}},
        ),
        ev(
            2,
            "Duel",
            TEAM_A,
            P_A1,
            location=[30, 40],
            **{"duel": {"type": {"name": "Tackle"}, "outcome": {"name": "Lost In Play"}}},
        ),
        ev(
            3,
            "Duel",
            TEAM_A,
            P_A1,
            location=[30, 40],
            **{"duel": {"type": {"name": "Aerial Lost"}}},
        ),
        ev(
            4,
            "Clearance",
            TEAM_A,
            P_A1,
            location=[10, 40],
            **{"clearance": {"aerial_won": True, "head": True}},
        ),
        ev(
            5,
            "Interception",
            TEAM_A,
            P_A1,
            location=[30, 40],
            **{"interception": {"outcome": {"name": "Won"}}},
        ),
        ev(
            6,
            "Interception",
            TEAM_A,
            P_A1,
            location=[30, 40],
            **{"interception": {"outcome": {"name": "Lost Out"}}},
        ),
        ev(7, "Block", TEAM_A, P_A1, location=[30, 40]),
        ev(
            8,
            "Ball Recovery",
            TEAM_A,
            P_A1,
            location=[30, 40],
            **{"ball_recovery": {"recovery_failure": True}},
        ),
        ev(9, "Ball Recovery", TEAM_A, P_A1, location=[30, 40]),
        ev(10, "Dribbled Past", TEAM_A, P_A1, location=[30, 40]),
        ev(11, "50/50", TEAM_A, P_A1, location=[30, 40], **{"50_50": {"outcome": {"name": "Won"}}}),
    ]
    m = compute_match_metrics(events)[P_A1]
    assert m["tackles"] == 2 and m["tackles_won"] == 1
    assert m["aerial_duels"] == 2 and m["aerial_duels_won"] == 1
    assert m["interceptions"] == 2 and m["interceptions_won"] == 1
    assert m["ball_recoveries"] == 1
    assert m["defensive_actions"] == 2 + 2 + 1 + 1
    assert m["ground_duels"] == 2 + 0 + 1 + 1 and m["ground_duels_won"] == 1 + 0 + 1
    assert "fifty_fifties" not in m


def test_touches_exclude_incomplete_receipts_and_count_box():
    events = [
        ev(1, "Ball Receipt*", TEAM_A, P_A1, location=[110, 40]),
        ev(
            2,
            "Ball Receipt*",
            TEAM_A,
            P_A1,
            location=[110, 40],
            **{"ball_receipt": {"outcome": {"name": "Incomplete"}}},
        ),
        ev(3, "Carry", TEAM_A, P_A1, location=[110, 40], **{"carry": {"end_location": [112, 40]}}),
        ev(4, "Miscontrol", TEAM_A, P_A1, location=[50, 40]),
    ]
    m = compute_match_metrics(events)[P_A1]
    assert m["touches"] == 3
    assert m["touches_att_box"] == 2
    assert m["miscontrols"] == 1


def test_goalkeeper_metrics_and_gk_passing():
    events = [
        ev(
            1,
            "Goal Keeper",
            TEAM_B,
            P_B_GK,
            position_id=1,
            **{"goalkeeper": {"type": {"name": "Shot Saved"}, "outcome": {"name": "Success"}}},
        ),
        ev(
            2,
            "Goal Keeper",
            TEAM_B,
            P_B_GK,
            position_id=1,
            **{"goalkeeper": {"type": {"name": "Goal Conceded"}, "outcome": {"name": "No Touch"}}},
        ),
        ev(
            3,
            "Goal Keeper",
            TEAM_B,
            P_B_GK,
            position_id=1,
            **{"goalkeeper": {"type": {"name": "Penalty Saved"}}},
        ),
        ev(
            4,
            "Goal Keeper",
            TEAM_B,
            P_B_GK,
            position_id=1,
            **{"goalkeeper": {"type": {"name": "Keeper Sweeper"}, "outcome": {"name": "Clear"}}},
        ),
        ev(
            5,
            "Goal Keeper",
            TEAM_B,
            P_B_GK,
            position_id=1,
            **{"goalkeeper": {"type": {"name": "Collected"}}},
        ),
        ev(
            6,
            "Goal Keeper",
            TEAM_B,
            P_B_GK,
            position_id=1,
            **{"goalkeeper": {"type": {"name": "Shot Faced"}}},
        ),
        ev(
            7,
            "Pass",
            TEAM_B,
            P_B_GK,
            position_id=1,
            location=[5, 40],
            **{"pass": {"end_location": [60, 40], "length": 55}},
        ),
        ev(
            8,
            "Pass",
            TEAM_B,
            P_B_GK,
            position_id=1,
            location=[5, 40],
            **{"pass": {"end_location": [20, 40], "length": 15, "outcome": {"name": "Incomplete"}}},
        ),
    ]
    m = compute_match_metrics(events)[P_B_GK]
    assert m["gk_shots_faced"] == 4
    assert m["gk_saves"] == 2 and m["gk_goals_conceded"] == 1
    assert m["gk_penalties_faced"] == 1 and m["gk_penalties_saved"] == 1
    assert m["gk_sweeper_actions"] == 1 and m["gk_claims"] == 1
    assert m["gk_passes"] == 2 and m["gk_passes_completed"] == 1 and m["gk_long_passes"] == 1
    assert "gk_psxg" not in m  # never derived from open data


def test_missing_xg_field_does_not_crash():
    events = [
        ev(
            1,
            "Shot",
            TEAM_A,
            P_A1,
            location=[100, 40],
            **{"shot": {"outcome": {"name": "Off T"}, "type": {"name": "Open Play"}}},
        )
    ]
    m = compute_match_metrics(events)[P_A1]
    assert m["shots"] == 1 and m["xg"] == 0.0


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ([50, 40], [62, 40], 1),  # +12 yards from x>=48
        ([30, 40], [50, 40], 0),  # starts in own 40%
        ([100, 30], [104, 40], 1),  # into box
        ([104, 40], [110, 40], 0),  # already in box, < 10 yards
    ],
)
def test_progressive_carries(start, end, expected):
    events = [ev(1, "Carry", TEAM_A, P_A1, location=start, **{"carry": {"end_location": end}})]
    assert compute_match_metrics(events)[P_A1].get("progressive_carries", 0) == expected
