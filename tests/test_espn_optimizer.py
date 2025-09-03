import sys
from pathlib import Path
from unittest.mock import Mock

# Ensure src directory is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nf_llm.fantasy_football.espn_optimizer import build_optimal_lineup


def test_build_optimal_lineup_recommends_free_agent():
    def make_player(pos, name, pts):
        p = Mock()
        p.position = pos
        p.name = name
        p.projected_points = pts
        return p

    qb1 = make_player("QB", "QB1", 15)
    qb2 = make_player("QB", "QB2", 10)
    rb1 = make_player("RB", "RB1", 12)
    rb2 = make_player("RB", "RB2", 8)
    wr1 = make_player("WR", "WR1", 9)
    wr2 = make_player("WR", "WR2", 7)
    wr3 = make_player("WR", "WR3", 6)
    te1 = make_player("TE", "TE1", 5)
    dst = make_player("DST", "DST", 4)

    team = Mock()
    team.roster = [qb1, qb2, rb1, rb2, wr1, wr2, wr3, te1, dst]

    settings = Mock()
    settings.roster_positions = [
        {"position": "QB", "count": 1},
        {"position": "RB", "count": 2},
        {"position": "WR", "count": 2},
        {"position": "TE", "count": 1},
        {"position": "RB/WR/TE", "count": 1},
        {"position": "DST", "count": 1},
    ]
    league = Mock()
    league.settings = settings

    fa_better = make_player("WR", "FA_WR", 11)
    league.free_agents.return_value = [fa_better]

    result = build_optimal_lineup(team, league, week=1, limit=5)
    assert any(p["name"] == "FA_WR" for p in result["lineup"]["WR"])
    assert result["pickups"] == [
        {
            "add": "FA_WR",
            "position": "WR",
            "slot": "WR",
            "drop": "WR2",
            "projected_points_gain": 4.0,
        }
    ]
