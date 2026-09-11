from data_pipeline.ingestion.statsbomb.minutes import (
    compute_appearances,
    parse_clock,
    period_durations,
)
from tests.conftest import TEAM_A, TEAM_B, ev, lineup_player, seg


def _lineups(players_a, players_b=None):
    return [
        {"team_id": TEAM_A, "team_name": "A", "lineup": players_a},
        {"team_id": TEAM_B, "team_name": "B", "lineup": players_b or []},
    ]


def test_parse_clock():
    assert parse_clock("89:15") == 89.25
    assert parse_clock("00:00") == 0.0
    assert parse_clock(None) is None


def test_period_durations_from_half_end(half_end_events):
    d = period_durations(half_end_events)
    assert d[1] == 47.05
    assert abs(d[2] - 50.0333) < 1e-3


def test_full_match_nominal_90_elapsed_includes_stoppage(half_end_events):
    lu = _lineups([lineup_player(1, [seg(21, "00:00", None, 1, None)])])
    apps, clock = compute_appearances(lu, half_end_events)
    a = apps[0]
    assert a.minutes_nominal == 90.0
    assert abs(a.minutes_elapsed - 97.08) < 0.01
    assert a.started is True
    assert a.minutes_by_position_id == {21: 90.0}
    assert clock.total_nominal == 90.0


def test_substitute_late_in_second_half(half_end_events):
    """Starter off at 89:15, sub on: starter 89.25 nominal, sub 0.75 nominal but ~5.8 elapsed."""
    starter = lineup_player(
        1, [seg(21, "00:00", "89:15", 1, 2, end_reason="Substitution - Off (Tactical)")]
    )
    sub = lineup_player(
        2, [seg(21, "89:15", None, 2, None, start_reason="Substitution - On (Tactical)")]
    )
    apps, _ = compute_appearances(_lineups([starter, sub]), half_end_events)
    by = {a.player_id: a for a in apps}
    assert by[1].minutes_nominal == 89.25
    assert by[2].minutes_nominal == 0.75
    assert by[2].started is False
    assert abs(by[2].minutes_elapsed - (50.0333 - 44.25)) < 0.01
    assert abs(by[1].minutes_nominal + by[2].minutes_nominal - 90.0) < 1e-9


def test_tactical_shift_splits_minutes_by_position(half_end_events):
    p = lineup_player(
        1,
        [
            seg(11, "00:00", "45:00", 1, 1, end_reason="Tactical Shift"),
            seg(5, "45:00", None, 2, None, start_reason="Tactical Shift"),
        ],
    )
    apps, _ = compute_appearances(_lineups([p]), half_end_events)
    a = apps[0]
    assert a.minutes_nominal == 90.0
    assert a.minutes_by_position_id == {11: 45.0, 5: 45.0}


def test_zero_length_segment_is_harmless(half_end_events):
    p = lineup_player(
        1,
        [
            seg(
                11,
                "45:00",
                "45:00",
                2,
                2,
                start_reason="Tactical Shift",
                end_reason="Substitution - On (Tactical)",
            ),
            seg(5, "45:00", None, 2, None, start_reason="Substitution - On (Tactical)"),
        ],
    )
    apps, _ = compute_appearances(_lineups([p]), half_end_events)
    assert apps[0].minutes_nominal == 45.0
    assert apps[0].minutes_by_position_id == {5: 45.0}
    assert apps[0].started is False


def test_red_card_ends_minutes_and_is_flagged(half_end_events):
    p = lineup_player(
        1,
        [seg(4, "00:00", "60:00", 1, 2, end_reason="Foul Committed (Second Yellow)")],
        cards=[
            {"time": "30:00", "card_type": "Yellow Card", "reason": "Foul", "period": 1},
            {"time": "60:00", "card_type": "Second Yellow", "reason": "Foul", "period": 2},
        ],
    )
    apps, _ = compute_appearances(_lineups([p]), half_end_events)
    assert apps[0].minutes_nominal == 60.0
    assert apps[0].red_card is True
    assert apps[0].yellow_cards == 2


def test_extra_time_and_shootout():
    events = [
        ev(1, "Half End", TEAM_A, period=1, ts="00:46:00.000"),
        ev(2, "Half End", TEAM_A, period=2, ts="00:48:00.000"),
        ev(3, "Half End", TEAM_A, period=3, ts="00:16:00.000"),
        ev(4, "Half End", TEAM_A, period=4, ts="00:17:00.000"),
        ev(5, "Half End", TEAM_A, period=5, ts="00:05:00.000"),
    ]
    p = lineup_player(1, [seg(1, "00:00", None, 1, None)])
    apps, clock = compute_appearances(_lineups([p]), events)
    assert clock.total_nominal == 120.0
    assert apps[0].minutes_nominal == 120.0
    assert abs(apps[0].minutes_elapsed - (46 + 48 + 16 + 17)) < 1e-9
    assert 5 not in clock.durations


def test_ninety_minute_player_edge_case(half_end_events):
    """A player with exactly one full match must produce exactly 90 nominal minutes (per-90 base)."""
    p = lineup_player(1, [seg(23, "00:00", None, 1, None)])
    apps, _ = compute_appearances(_lineups([p]), half_end_events)
    assert apps[0].minutes_nominal == 90.0


def test_missing_half_end_falls_back_to_nominal():
    events = [ev(1, "Pass", TEAM_A, player=1, period=1), ev(2, "Pass", TEAM_A, player=1, period=2)]
    p = lineup_player(1, [seg(23, "00:00", None, 1, None)])
    apps, clock = compute_appearances(_lineups([p]), events)
    assert clock.durations == {1: 45.0, 2: 45.0}
    assert apps[0].minutes_elapsed == 90.0
