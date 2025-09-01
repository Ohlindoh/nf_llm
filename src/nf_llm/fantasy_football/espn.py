"""Utilities for retrieving ESPN fantasy football data."""
from __future__ import annotations

from typing import Any, Dict, List

try:  # pragma: no cover - import guard for optional dependency
    from espn_api.football import League  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    League = None  # type: ignore


def _normalise_id(identifier: str | dict) -> str:
    """Return an ESPN identifier in normalised form.

    IDs returned by the API may include surrounding braces or differ in case.  By
    stripping the braces and lowering the case we can compare identifiers
    reliably.
    
    Parameters
    ----------
    identifier: str | dict
        Either a string SWID or a dict containing owner information with SWID.
    """
    if isinstance(identifier, dict):
        # Extract SWID from owner dict - try common keys
        swid = identifier.get('swid') or identifier.get('SWID') or identifier.get('id', '')
        if isinstance(swid, str):
            return swid.strip("{}").lower()
        return str(swid).strip("{}").lower()
    
    return str(identifier).strip("{}").lower()


def _find_user_team(league: Any, swid: str) -> Any:
    """Locate the team object belonging to the user identified by ``swid``.

    The espn-api library sets ``league.team_id`` only for primary managers.  When
    the user is a co-manager the library falls back to the first team in the
    league.  To ensure the correct team is returned we scan each team's owners
    for the provided ``swid``.
    """

    normalised = _normalise_id(swid)
    for team in getattr(league, "teams", []):
        owners = getattr(team, "owners", []) or []
        for owner in owners:
            if _normalise_id(owner) == normalised:
                return team

    # Fallback to the team detected by the library if no owner match is found.
    team_id = getattr(league, "team_id", None)
    return next(
        (t for t in getattr(league, "teams", []) if getattr(t, "team_id", None) == team_id),
        None,
    )


def get_user_team(league_id: int, year: int, swid: str, espn_s2: str) -> List[Dict[str, Any]]:
    """Return the roster for the team associated with the provided credentials.

    The function now supports both primary managers and co-managers by searching
    the league's teams for one that lists the provided ``swid`` as an owner.
    """

    if League is None:  # pragma: no cover - dependency not installed
        raise ImportError("espn-api package is required to fetch ESPN data")

    league = League(league_id=league_id, year=year, swid=swid, espn_s2=espn_s2)
    team = _find_user_team(league, swid)
    if team is None:
        raise ValueError("Could not determine team for provided credentials")

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


def recommend_lineup(team: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Suggest a starting lineup based on projected points.

    Parameters
    ----------
    team: Any
        Team object returned by ``espn-api``.

    Returns
    -------
    dict
        Mapping of lineup slot to selected player dictionaries.  Only a simple
        heuristic is used: the highest ``projected_points`` players are chosen
        for each position with a single FLEX spot (RB/WR/TE).
    """

    slots = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1, "FLEX": 1}
    flex_positions = {"RB", "WR", "TE"}
    lineup: Dict[str, List[Dict[str, Any]]] = {slot: [] for slot in slots}

    players = sorted(
        getattr(team, "roster", []),
        key=lambda p: getattr(p, "projected_points", 0),
        reverse=True,
    )

    for player in players:
        pos = getattr(player, "position", "")
        if pos in slots and len(lineup[pos]) < slots[pos]:
            lineup[pos].append(
                {
                    "name": getattr(player, "name", ""),
                    "position": pos,
                    "projected_points": getattr(player, "projected_points", 0),
                }
            )
        elif pos in flex_positions and len(lineup["FLEX"]) < slots["FLEX"]:
            lineup["FLEX"].append(
                {
                    "name": getattr(player, "name", ""),
                    "position": pos,
                    "projected_points": getattr(player, "projected_points", 0),
                }
            )

    return lineup


def get_matchup(league: Any, team_id: int, week: int | None = None) -> Any:
    """Return the opponent for ``team_id`` in the given ``week``.

    Parameters
    ----------
    league: Any
        ``League`` object from ``espn-api``.
    team_id: int
        Identifier of the user's team.
    week: int, optional
        Week to fetch matchup information for.  Defaults to the current week as
        determined by ``espn-api``.
    """

    for box in getattr(league, "box_scores", lambda w: [])(week):
        if getattr(getattr(box, "home_team", None), "team_id", None) == team_id:
            return getattr(box, "away_team", None)
        if getattr(getattr(box, "away_team", None), "team_id", None) == team_id:
            return getattr(box, "home_team", None)
    return None


def suggest_free_agents(
    league: Any, team: Any, week: int | None = None, limit: int = 5
) -> List[Dict[str, Any]]:
    """Return free agents projected to outperform current rostered players.

    A simple comparison is performed: if a free agent's ``projected_points``
    exceeds the lowest projected player on the roster at the same position the
    free agent is recommended.
    """

    roster_by_pos: Dict[str, List[float]] = {}
    for player in getattr(team, "roster", []):
        pos = getattr(player, "position", "")
        roster_by_pos.setdefault(pos, []).append(
            float(getattr(player, "projected_points", 0))
        )

    suggestions: List[Dict[str, Any]] = []
    for fa in getattr(league, "free_agents", lambda **_: [])(week=week):
        pos = getattr(fa, "position", "")
        proj = float(getattr(fa, "projected_points", 0))
        worst = min(roster_by_pos.get(pos, [float("inf")]))
        if proj > worst:
            suggestions.append(
                {
                    "name": getattr(fa, "name", ""),
                    "position": pos,
                    "projected_points": proj,
                }
            )

    suggestions.sort(key=lambda p: p["projected_points"], reverse=True)
    return suggestions[:limit]
