"""Utilities for retrieving ESPN fantasy football data."""
from __future__ import annotations

from typing import Any, List, Dict

try:  # pragma: no cover - import guard for optional dependency
    from espn_api.football import League  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    League = None  # type: ignore


def get_user_team(league_id: int, year: int, swid: str, espn_s2: str) -> List[Dict[str, Any]]:
    """Return the roster for the team associated with the provided credentials.

    Parameters
    ----------
    league_id: int
        ESPN league identifier.
    year: int
        Season year of the league.
    swid: str
        SWID token from the user's ESPN cookies.
    espn_s2: str
        ESPN_S2 token from the user's ESPN cookies.

    Returns
    -------
    list of dict
        Each dict contains player information such as ``name`` and ``position``.
    """
    if League is None:  # pragma: no cover - dependency not installed
        raise ImportError("espn-api package is required to fetch ESPN data")

    league = League(league_id=league_id, year=year, swid=swid, espn_s2=espn_s2)
    team_id = getattr(league, "team_id", None)
    if team_id is None:
        raise ValueError("Could not determine team for provided credentials")

    team = next((t for t in league.teams if getattr(t, "team_id", None) == team_id), None)
    if team is None:
        raise ValueError(f"Team {team_id} not found in league {league_id}")

    roster: List[Dict[str, Any]] = []
    for player in getattr(team, "roster", []):
        roster.append(
            {
                "name": getattr(player, "name", ""),
                "position": getattr(player, "position", ""),
                "proTeam": getattr(player, "proTeam", ""),
            }
        )
    return roster
