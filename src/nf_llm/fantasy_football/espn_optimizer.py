"""Lineup optimization utilities for ESPN fantasy football."""
from __future__ import annotations

from typing import Any, Dict, List

from .espn import lineup_slots, recommend_lineup, suggest_free_agents


def build_optimal_lineup(
    team: Any,
    league: Any,
    week: int | None = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Construct the optimal lineup and highlight impactful pickups.

    The function first generates a lineup from the current roster and then
    considers available free agents.  If a free agent projects for more points
    than the worst starter at a compatible position, they are inserted into the
    lineup and recorded as a pickup suggestion.
    """

    lineup = recommend_lineup(team, league)
    slots, flex_rules = lineup_slots(league)
    suggestions = suggest_free_agents(league, team, week=week, limit=limit)

    pickups: List[Dict[str, Any]] = []
    for fa in suggestions:
        pos = fa["position"]
        fa_points = fa["projected_points"]

        candidate_slots: List[str] = []
        if pos in lineup:
            candidate_slots.append(pos)
        for flex_slot, allowed in flex_rules.items():
            if pos in allowed:
                candidate_slots.append(flex_slot)

        best_slot = None
        best_player = None
        best_diff = 0.0
        for slot in candidate_slots:
            players = lineup.get(slot, [])
            if not players:
                diff = fa_points
                if diff > best_diff:
                    best_slot = slot
                    best_player = None
                    best_diff = diff
            else:
                worst = min(players, key=lambda p: p["projected_points"])
                diff = fa_points - worst["projected_points"]
                if diff > best_diff:
                    best_slot = slot
                    best_player = worst
                    best_diff = diff

        if best_slot and best_diff > 0:
            if best_player:
                lineup[best_slot].remove(best_player)
                drop_name = best_player["name"]
            else:
                drop_name = None
            lineup[best_slot].append(
                {
                    "name": fa["name"],
                    "position": pos,
                    "projected_points": fa_points,
                }
            )
            pickups.append(
                {
                    "add": fa["name"],
                    "position": pos,
                    "slot": best_slot,
                    "drop": drop_name,
                    "projected_points_gain": round(best_diff, 1),
                }
            )

    return {"lineup": lineup, "pickups": pickups}
