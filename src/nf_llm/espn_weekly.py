"""Command line utility for weekly ESPN fantasy football insights."""
from __future__ import annotations

import os
from datetime import datetime

try:  # pragma: no cover - optional dependency
    from espn_api.football import League  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    League = None  # type: ignore

from .fantasy_football.espn import (
    _find_user_team,
    get_matchup,
    recommend_lineup,
    suggest_free_agents,
)


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def main() -> None:
    if League is None:  # pragma: no cover - dependency not installed
        raise ImportError("espn-api package is required to fetch ESPN data")

    league_id = int(_env("LEAGUE_ID"))
    year = datetime.now().year
    swid = _env("SWID")
    espn_s2 = _env("ESPN_S2")

    league = League(league_id=league_id, year=year, swid=swid, espn_s2=espn_s2)
    team = _find_user_team(league, swid)
    if team is None:
        raise RuntimeError("Could not locate team for provided credentials")

    print("== Roster ==")
    for player in getattr(team, "roster", []):
        name = getattr(player, "name", "")
        pos = getattr(player, "position", "")
        proj = getattr(player, "projected_points", 0)
        print(f"{pos:>3}  {name:<25} {proj:5.1f}")

    print("\n== Suggested Lineup ==")
    lineup = recommend_lineup(team, league)
    for slot, players in lineup.items():
        for p in players:
            print(f"{slot:>5}: {p['name']} ({p['position']}) {p['projected_points']:.1f}")

    opp = get_matchup(league, getattr(team, "team_id", 0))
    if opp is not None:
        print("\n== Matchup ==")
        print(f"Vs. {getattr(opp, 'team_name', 'Unknown')}")

    print("\n== Free Agent Suggestions ==")
    for fa in suggest_free_agents(league, team):
        print(
            f"{fa['position']:>3}  {fa['name']:<25} {fa['projected_points']:.1f}"
        )


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
