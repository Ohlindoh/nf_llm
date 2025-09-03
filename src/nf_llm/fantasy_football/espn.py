"""Utilities for retrieving ESPN fantasy football data."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Set

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
    for the provided ``swid``.  Some test doubles may not provide an iterable
    ``owners`` attribute; in that case we simply treat the team as having no
    owners rather than raising ``TypeError``.
    """

    normalised = _normalise_id(swid)
    for team in getattr(league, "teams", []):
        owners = getattr(team, "owners", []) or []
        try:
            owner_iter = list(owners)
        except TypeError:
            owner_iter = []
        for owner in owner_iter:
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


def _lineup_slots(league: Any | None) -> Tuple[Dict[str, int], Dict[str, Set[str]]]:
    """Return lineup slot counts and flex rules for ``league``.

    The espn-api exposes roster settings describing how many players are allowed
    at each slot.  The structure of this data can vary slightly so the helper is
    defensive and falls back to a sensible default when the information is
    missing.
    """

    if league is None:
        return (
            {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "DST": 1, "FLEX": 1},
            {"FLEX": {"RB", "WR", "TE"}},
        )

    settings = getattr(league, "settings", None)
    roster_positions = getattr(settings, "roster_positions", []) if settings else []

    slots: Dict[str, int] = {}
    flex: Dict[str, Set[str]] = {}

    for item in roster_positions:
        if isinstance(item, dict):
            name = str(
                item.get("position")
                or item.get("slot")
                or item.get("name")
                or ""
            ).upper()
            count = int(item.get("count", item.get("num", 0)))
        else:
            name = str(
                getattr(item, "position", getattr(item, "slot", getattr(item, "name", "")))
            ).upper()
            count = int(getattr(item, "count", getattr(item, "num", 0)))

        if count <= 0 or name in {"BE", "BN", "BENCH", "IR"}:
            continue

        if "/" in name:
            allowed = {p.strip().upper() for p in name.split("/")}
            slot_name = "OP" if allowed == {"QB", "RB", "WR", "TE"} else "FLEX"
            slots[slot_name] = slots.get(slot_name, 0) + count
            flex[slot_name] = flex.get(slot_name, allowed)
        elif name == "OP":
            slots["OP"] = slots.get("OP", 0) + count
            flex["OP"] = {"QB", "RB", "WR", "TE"}
        else:
            if name in {"D/ST", "DST"}:
                name = "DST"
            slots[name] = slots.get(name, 0) + count

    if "FLEX" in slots and "FLEX" not in flex:
        flex["FLEX"] = {"RB", "WR", "TE"}

    return slots, flex


def recommend_lineup(team: Any, league: Any | None = None) -> Dict[str, List[Dict[str, Any]]]:
    """Suggest a starting lineup based on projected points.

    ``league`` may be provided to determine the roster configuration; if absent
    a standard configuration with a single FLEX spot is used.
    """

    slots, flex_rules = _lineup_slots(league)
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
            continue

        for flex_slot, allowed in flex_rules.items():
            if pos in allowed and len(lineup[flex_slot]) < slots[flex_slot]:
                lineup[flex_slot].append(
                    {
                        "name": getattr(player, "name", ""),
                        "position": pos,
                        "projected_points": getattr(player, "projected_points", 0),
                    }
                )
                break

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
