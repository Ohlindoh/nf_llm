# src/nf_llm/service.py
"""
Thin service layer that the API (or any other client) can call.
Keeps LineupOptimizer details out of the HTTP layer.
"""

from pathlib import Path
from typing import Any

import pandas as pd

from nf_llm.data_io import preprocess_data
from nf_llm.optimizer import LineupOptimizer

try:  # pragma: no cover - optional dependency
    from espn_api.football import League
except Exception:  # pragma: no cover - handled at runtime
    League = None


def build_lineups(
    csv_path: str,
    slate_id: str,
    constraints: dict[str, Any],
) -> list[dict]:
    """
    Parameters
    ----------
    csv_path : str
        Path to the player CSV (relative or absolute).
    slate_id : str
        Identifier you care about (passed through for logging;
        optimiser ignores it for now).
    constraints : dict
        Same structure Streamlit already builds: num_lineups,
        max_exposure, must_include, etc.

    Returns
    -------
    list[dict]  # JSON‑serialisable line‑ups
    """
    # --- 1. Load data ---
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

    df = pd.read_csv(csv_file)
    df = preprocess_data(df)

    # --- 2. Run optimiser ---
    opt = LineupOptimizer(df)
    lineups = opt.generate_lineups(constraints=constraints)

    # --- 3. Return plain Python objects (already JSON‑safe) ---
    return lineups


def get_undervalued_players_data(
    csv_path: str, top_n: int = 5
) -> dict[str, list[dict]]:
    """
    Get most undervalued players by position.

    Parameters
    ----------
    csv_path : str
        Path to the player CSV file
    top_n : int
        Number of top players per position to return

    Returns
    -------
    dict
        Dictionary with position keys and lists of player data
    """
    # Load and preprocess data
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

    df = pd.read_csv(csv_path)
    df = preprocess_data(df)

    undervalued = {}
    for position in ["QB", "RB", "WR", "TE", "DST"]:
        position_data = df[df["player_position_id"] == position].sort_values(
            "value", ascending=False
        )
        # Convert to list of dicts for JSON serialization
        players_list = position_data.head(top_n)[
            ["player_name", "team", "salary", "projected_points", "value"]
        ].to_dict("records")
        undervalued[position] = players_list

    return undervalued


# ---------------------------------------------------------------------------
# ESPN weekly plan
# ---------------------------------------------------------------------------


def _parse_preferences(text: str) -> dict[str, float]:
    """Very small helper to convert natural language hints to numeric nudges."""
    prefs: dict[str, float] = {}
    if not text:
        return prefs

    low = text.lower()
    if "avoid q" in low:
        prefs["injury_penalty_pts"] = 1.0
    if "floor" in low:
        prefs["variance_penalty_pts"] = 0.5
    if "dome" in low:
        prefs["dome_bonus_pts"] = 0.3
    return prefs


def _player_to_dict(player) -> dict[str, Any]:
    return {
        "name": getattr(player, "name", ""),
        "pos": getattr(player, "position", ""),
        "team": getattr(player, "proTeam", ""),
        "injury_status": getattr(player, "injuryStatus", None),
        "proj": getattr(player, "projected_points", 0) or 0,
    }


def compute_weekly_plan(
    league_id: str,
    year: int,
    espn_s2: str,
    swid: str,
    preferences_text: str | None = None,
    max_acquisitions: int = 2,
    positions_to_fill: list[str] | None = None,
) -> dict[str, Any]:
    """Compute start/sit and acquisition recommendations using ESPN data."""

    if League is None:  # pragma: no cover - runtime guard
        raise RuntimeError("espn_api package is required for weekly plan")

    league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)

    # ---- Step 1: league state ----
    current_week = getattr(league, "current_week", None)

    # Identify the user's team. Fall back to first team if not found.
    user_team = None
    for team in league.teams:
        owners = [str(o).lower().strip("{}") for o in getattr(team, "owners", [])]
        if swid.lower().strip("{}") in owners:
            user_team = team
            break
    if user_team is None:
        user_team = league.teams[0]

    your_roster = [_player_to_dict(p) for p in user_team.roster]
    starters = {}
    bench = []
    starter_objs = getattr(user_team, "starters", [])
    for p in starter_objs:
        slot = getattr(p, "slot_position", getattr(p, "position", ""))
        starters[slot] = _player_to_dict(p)
    roster_ids = {id(p) for p in starter_objs}
    bench = [_player_to_dict(p) for p in user_team.roster if id(p) not in roster_ids]

    available_players = []
    try:
        fa_players = league.free_agents(size=500)
        available_players = [_player_to_dict(p) for p in fa_players]
    except Exception:
        available_players = []

    # ---- Step 2: league rules ----
    settings = getattr(league, "settings", None)
    slots = getattr(settings, "roster_positions", {}) if settings else {}
    scoring = getattr(settings, "scoring_settings", {}) if settings else {}
    flags = {
        "has_superflex": "OP" in slots if isinstance(slots, dict) else False,
        "te_premium": False,
        "return_scoring": False,
    }
    league_profile = {"slots": slots, "scoring": scoring, "flags": flags}

    # ---- Step 3: preferences ----
    prefs = _parse_preferences(preferences_text or "")
    notes = []
    if prefs.get("injury_penalty_pts"):
        notes.append("Preferences applied: avoid Q tags (+1.0 penalty)")
    if prefs.get("variance_penalty_pts"):
        notes.append("Preferences applied: prefer floor (+0.5)")
    if prefs.get("dome_bonus_pts"):
        notes.append("Preferences applied: ok to chase dome games (+0.3)")

    def adjusted_proj(p_dict: dict[str, Any]) -> float:
        proj = p_dict["proj"]
        if p_dict.get("injury_status") == "QUESTIONABLE":
            proj -= prefs.get("injury_penalty_pts", 0)
        proj -= prefs.get("variance_penalty_pts", 0)
        proj += prefs.get("dome_bonus_pts", 0)
        return proj

    for p in your_roster:
        p["adj_proj_wk"] = adjusted_proj(p)
    for p in available_players:
        p["adj_proj_wk"] = adjusted_proj(p)

    # ---- Step 4 & 5: simple optimiser ----
    # Baseline lineup using greedy assignment
    slot_order: list[str] = []
    if isinstance(slots, dict):
        for slot, count in slots.items():
            slot_order.extend([slot] * count)
    else:
        slot_order = list(slots)

    remaining = your_roster.copy()
    chosen: dict[str, dict[str, Any]] = {}
    used = set()
    for slot in slot_order:
        eligible = [p for p in remaining if p["pos"] == slot and id(p) not in used]
        if slot == "FLEX":
            eligible = [
                p
                for p in remaining
                if p["pos"] in {"RB", "WR", "TE"} and id(p) not in used
            ]
        if slot == "OP":
            eligible = [
                p
                for p in remaining
                if p["pos"] in {"QB", "RB", "WR", "TE"} and id(p) not in used
            ]
        if eligible:
            best = max(eligible, key=lambda p: p.get("adj_proj_wk", 0))
            chosen[slot] = best
            used.add(id(best))
    bench = [p for p in remaining if id(p) not in used]

    # Acquisition suggestions: replace worst starter if FA has higher projection
    acquisitions = []
    starters_list = list(chosen.items())
    for cand in sorted(
        available_players, key=lambda p: p.get("adj_proj_wk", 0), reverse=True
    )[:25]:
        repl_player = None
        for slot, starter in starters_list:
            if (
                slot == cand["pos"]
                or (slot == "FLEX" and cand["pos"] in {"RB", "WR", "TE"})
                or (slot == "OP" and cand["pos"] in {"QB", "RB", "WR", "TE"})
            ):
                if (
                    repl_player is None
                    or starter["adj_proj_wk"] < repl_player["adj_proj_wk"]
                ):
                    repl_player = starter
        if repl_player and cand["adj_proj_wk"] > repl_player["adj_proj_wk"]:
            delta = cand["adj_proj_wk"] - repl_player["adj_proj_wk"]
            why = (
                f"Proj {cand['adj_proj_wk']:.1f} "
                f"vs {repl_player['adj_proj_wk']:.1f} "
                f"(+{delta:.1f})"
            )
            acquisitions.append(
                {
                    "name": cand["name"],
                    "pos": cand["pos"],
                    "team": cand["team"],
                    "status": getattr(cand, "status", "FA"),
                    "adj_proj_wk": cand["adj_proj_wk"],
                    "par_op": delta,
                    "delta_points_if_acquired": delta,
                    "why": why,
                }
            )
            if len(acquisitions) >= max_acquisitions:
                break

    start_sit = {"starters": chosen, "bench": bench, "deltas": {}}

    return {
        "meta": {"current_week": current_week, "has_superflex": flags["has_superflex"]},
        "league_profile": league_profile,
        "start_sit": start_sit,
        "acquisitions": acquisitions,
        "notes": notes,
    }
