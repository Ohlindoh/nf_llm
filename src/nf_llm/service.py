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


def _infer_slate_id(csv_file: Path, df: pd.DataFrame) -> str:
    """Derive a slate identifier from the salary CSV.

    Preference order:
      1) Non-empty `slate_id` column in the CSV (first row)
      2) Filename: collectors use `<slate_id>_raw.csv`; trim `_raw`
    """
    for col in df.columns:
        if col.lower() == "slate_id" and not df[col].isna().all():
            value = df[col].iloc[0]
            if isinstance(value, str) and value:
                return value

    name = csv_file.stem
    if name.endswith("_raw"):
        name = name[:-4]
    if not name:
        raise ValueError("Unable to infer slate_id from salary CSV")
    return name


def build_lineups(
    csv_path: str,
    constraints: dict[str, Any],
) -> tuple[list[dict], str]:
    """
    Parameters
    ----------
    csv_path : str
        Path to the player CSV (relative or absolute).
    constraints : dict
        Same structure Streamlit already builds: num_lineups, max_exposure,
        must_include, etc.

    Returns
    -------
    (lineups, slate_id) : tuple[list[dict], str]
        Generated lineups and the inferred ``slate_id``.
    """
    # --- 1. Load data ---
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

    raw_df = pd.read_csv(csv_file)
    slate_id = _infer_slate_id(csv_file, raw_df)
    df = preprocess_data(raw_df)

    # --- 2. Run optimiser ---
    opt = LineupOptimizer(df)
    lineups = opt.generate_lineups(constraints=constraints)

    # --- 3. Return generated lineups with slate identifier ---
    return lineups, slate_id


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

    undervalued: dict[str, list[dict]] = {}
    for position in ["QB", "RB", "WR", "TE", "DST"]:
        position_data = df[df["player_position_id"] == position].sort_values(
            "value", ascending=False
        )
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
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

    df = pd.read_csv(csv_file)
    df = preprocess_data(df)

    opt = LineupOptimizer(df)
    results = opt.benchmark_scenario_counts(
        constraints=constraints or {},
        test_counts=test_counts,
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
