# src/nf_llm/service.py
"""
Thin service layer that the API (or any other client) can call.
Keeps LineupOptimizer details out of the HTTP layer.
"""

import os
from pathlib import Path
from typing import Any

import pandas as pd

from nf_llm.data_io import preprocess_data
from nf_llm.optimizer import LineupOptimizer


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
        Identifier you care about (passed through for logging; optimiser ignores it for now).
    constraints : dict
        Same structure Streamlit already builds: num_lineups, max_exposure, must_include, etc.

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


def benchmark_optimization(
    csv_path: str,
    slate_id: str,
    constraints: dict[str, Any] = None,
    test_counts: list[int] = None,
) -> dict[str, Any]:
    """
    Benchmark different scenario counts to find optimal performance/quality trade-off.
    
    Parameters
    ----------
    csv_path : str
        Path to the player CSV file
    slate_id : str
        Identifier for the slate (for logging)
    constraints : dict, optional
        Optimization constraints
    test_counts : list, optional
        List of scenario counts to test (default: [10, 25, 50, 75, 100])
    
    Returns
    -------
    dict
        Benchmark results with performance metrics for each scenario count
    """
    # Load data
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

    df = pd.read_csv(csv_file)
    df = preprocess_data(df)

    # Run benchmark
    opt = LineupOptimizer(df)
    results = opt.benchmark_scenario_counts(
        constraints=constraints or {},
        test_counts=test_counts
    )

    return results


def _load_dk_player_ids(slate_id: str) -> set[str]:
    """Load DraftKings player identifiers for a slate.

    Looks for a raw DraftKings salary file produced by the data collectors
    and returns a set of player identifiers. We include multiple identifier
    columns (playerId, playerDkId, draftableId) to be tolerant of whichever
    ID DraftKings requires for uploads.
    """

    base_dir = Path(os.getenv("DK_SALARIES_DIR", "data/raw/dk_salaries"))
    salary_file = base_dir / f"{slate_id}_raw.csv"
    if not salary_file.exists():
        raise FileNotFoundError(f"Slate data not found: {salary_file}")

    df = pd.read_csv(salary_file, dtype=str)
    valid_ids: set[str] = set()
    for col in ["playerId", "playerDkId", "draftableId"]:
        if col in df.columns:
            valid_ids.update(df[col].dropna().astype(str))
    return valid_ids


def export_dk_csv(slate_id: str, lineups: list[list[str]]) -> tuple[str, list[int]]:
    """Validate lineups and produce a DraftKings upload CSV.

    Parameters
    ----------
    slate_id : str
        Identifier for the DraftKings slate. Used to locate salary data and
        validate player IDs.
    lineups : list[list[str]]
        Each inner list contains nine DraftKings player IDs in roster order.

    Returns
    -------
    tuple[str, list[int]]
        The CSV content as a string and a list of 1-based indices for any
        invalid lineups.
    """

    valid_ids = _load_dk_player_ids(slate_id)

    header = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
    csv_lines = [",".join(header)]
    invalid: list[int] = []

    for idx, lineup in enumerate(lineups, start=1):
        if len(lineup) != 9 or any(pid not in valid_ids for pid in lineup):
            invalid.append(idx)
            continue
        csv_lines.append(",".join(lineup))

    csv_content = "\n".join(csv_lines) + ("\n" if csv_lines else "")
    return csv_content, invalid
