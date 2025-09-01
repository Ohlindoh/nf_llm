import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Ensure src directory is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nf_llm.fantasy_football.espn import (
    get_user_team,
    get_matchup,
    recommend_lineup,
    suggest_free_agents,
)


def test_get_user_team_returns_roster():
    player = Mock()
    player.name = "Tom Brady"
    player.position = "QB"
    player.proTeam = "NE"

    team = Mock()
    team.team_id = 2
    team.roster = [player]

    league = Mock()
    league.team_id = 2
    league.teams = [team]

    with patch(
        "nf_llm.fantasy_football.espn.League", return_value=league
    ) as league_cls:
        roster = get_user_team(1, 2024, "swid", "espn_s2")

    league_cls.assert_called_once_with(
        league_id=1, year=2024, swid="swid", espn_s2="espn_s2"
    )
    assert roster == [
        {"name": "Tom Brady", "position": "QB", "proTeam": "NE"}
    ]


def test_get_user_team_handles_comanager():
    swid = "{USER}"  # swid with braces to test normalisation

    player = Mock()
    player.name = "Co QB"
    player.position = "QB"
    player.proTeam = "TB"

    team1 = Mock()
    team1.team_id = 1
    team1.owners = ["{OTHER}"]
    team1.roster = []

    team2 = Mock()
    team2.team_id = 2
    team2.owners = [swid, "{OTHER2}"]
    team2.roster = [player]

    league = Mock()
    league.team_id = 1  # library would incorrectly point to team1
    league.teams = [team1, team2]

    with patch("nf_llm.fantasy_football.espn.League", return_value=league):
        roster = get_user_team(1, 2024, swid, "token")

    assert roster == [{"name": "Co QB", "position": "QB", "proTeam": "TB"}]


def test_recommend_lineup_selects_best_players():
    qb1 = Mock(); qb1.position = "QB"; qb1.name = "QB1"; qb1.projected_points = 15
    qb2 = Mock(); qb2.position = "QB"; qb2.name = "QB2"; qb2.projected_points = 10
    rb1 = Mock(); rb1.position = "RB"; rb1.name = "RB1"; rb1.projected_points = 12
    rb2 = Mock(); rb2.position = "RB"; rb2.name = "RB2"; rb2.projected_points = 8
    wr1 = Mock(); wr1.position = "WR"; wr1.name = "WR1"; wr1.projected_points = 9
    wr2 = Mock(); wr2.position = "WR"; wr2.name = "WR2"; wr2.projected_points = 7
    wr3 = Mock(); wr3.position = "WR"; wr3.name = "WR3"; wr3.projected_points = 6
    te1 = Mock(); te1.position = "TE"; te1.name = "TE1"; te1.projected_points = 5
    dst = Mock(); dst.position = "DST"; dst.name = "DST"; dst.projected_points = 4

    team = Mock()
    team.roster = [qb1, qb2, rb1, rb2, wr1, wr2, wr3, te1, dst]

    lineup = recommend_lineup(team)
    assert lineup["QB"][0]["name"] == "QB1"
    assert len(lineup["RB"]) == 2
    assert len(lineup["WR"]) == 3
    assert lineup["TE"][0]["name"] == "TE1"
    assert lineup["DST"][0]["name"] == "DST"


def test_get_matchup_returns_opponent():
    team_id = 2
    opponent = Mock()
    opponent.team_id = 3

    box = Mock()
    box.home_team = Mock(team_id=team_id)
    box.away_team = opponent

    league = Mock()
    league.box_scores.return_value = [box]

    result = get_matchup(league, team_id, week=1)
    assert result is opponent


def test_suggest_free_agents_identifies_better_players():
    roster_player = Mock()
    roster_player.position = "RB"
    roster_player.projected_points = 5

    team = Mock()
    team.roster = [roster_player]

    fa_better = Mock()
    fa_better.name = "Better"
    fa_better.position = "RB"
    fa_better.projected_points = 10

    fa_worse = Mock()
    fa_worse.name = "Worse"
    fa_worse.position = "RB"
    fa_worse.projected_points = 3

    league = Mock()
    league.free_agents.return_value = [fa_better, fa_worse]

    suggestions = suggest_free_agents(league, team, week=1, limit=5)
    assert suggestions == [
        {"name": "Better", "position": "RB", "projected_points": 10.0}
    ]
