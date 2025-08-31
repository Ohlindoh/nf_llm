import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Ensure src directory is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nf_llm.fantasy_football.espn import get_user_team


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
