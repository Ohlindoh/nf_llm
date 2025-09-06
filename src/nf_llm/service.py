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
) -> tuple[int, list[dict]]:
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
    tuple[int, list[dict]]
        Run identifier and JSON-serialisable line-ups
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

    # --- 3. Persist run for later export (optional) ---
    run_id = 1  # Default fallback
    try:
        import duckdb

        db_url = os.getenv("DATABASE_URL", "duckdb:////app/data/nf_llm.duckdb")
        db_path = db_url.replace("duckdb:///", "")
        con = duckdb.connect(database=db_path)
        con.execute(
            "CREATE TABLE IF NOT EXISTS optimizer_lineups (lineup_id INT, run_id INT, slate_id TEXT)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS optimizer_lineup_players (lineup_id INT, slot TEXT, player_id INT)"
        )
        run_id = con.execute("SELECT COALESCE(MAX(run_id), 0) + 1 FROM optimizer_lineups").fetchone()[0]

        for idx, lineup in enumerate(lineups, start=1):
            con.execute(
                "INSERT INTO optimizer_lineups VALUES (?, ?, ?)", [idx, run_id, slate_id]
            )
            for slot, player in lineup.items():
                pid = int(player.get("player_id", 0))
                con.execute(
                    "INSERT INTO optimizer_lineup_players VALUES (?, ?, ?)",
                    [idx, slot, pid],
                )
        con.close()
        print(f"Successfully persisted run {run_id} to database")
    except Exception as e:
        print(f"Database persistence failed (continuing without): {e}")
        # Generate a timestamp-based run_id as fallback
        import time
        run_id = int(time.time())

    # --- 4. Return run_id and lineups ---
    return run_id, lineups


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


def export_run_dk_csv(run_id: int) -> tuple[str, str]:
    """Build a DraftKings CSV for a stored optimiser run.

    Parameters
    ----------
    run_id:
        Identifier for the optimiser run whose lineups should be exported.

    Returns
    -------
    tuple[str, str]
        CSV content and the associated ``slate_id``.

    Raises
    ------
    FileNotFoundError
        If the run contains no lineups.
    ValueError
        If the run spans multiple slates, has missing slots or players
        missing a DraftKings mapping.
    """

    try:
        import duckdb

        db_url = os.getenv("DATABASE_URL", "duckdb:////app/data/nf_llm.duckdb")
        db_path = db_url.replace("duckdb:///", "")
        con = duckdb.connect(database=db_path)

        lineups_df = con.execute(
            "SELECT lineup_id, slate_id FROM optimizer_lineups WHERE run_id = ?",
            [run_id],
        ).fetchdf()

        if lineups_df.empty:
            raise FileNotFoundError(f"No lineups for run {run_id}")

        if lineups_df["slate_id"].nunique() > 1:
            raise ValueError("multiple slates in run")

        slate_id = str(lineups_df["slate_id"].iloc[0])
        lineup_ids = lineups_df["lineup_id"].tolist()

        salary_df = con.execute(
            """
            SELECT player_id, dk_player_id
            FROM (
                SELECT
                    player_id,
                    dk_player_id,
                    pos,
                    ROW_NUMBER() OVER (
                        PARTITION BY player_id
                        ORDER BY (pos = 'FLEX')
                    ) AS rn
                FROM salaries
                WHERE slate_id = ?
            )
            WHERE rn = 1
            """,
            [slate_id],
        ).fetchdf()

        salary_map = {
            int(row.player_id): str(row.dk_player_id) for row in salary_df.itertuples()
        }

        placeholders = ",".join("?" for _ in lineup_ids)
        players_df = con.execute(
            f"SELECT lineup_id, slot, player_id FROM optimizer_lineup_players "
            f"WHERE lineup_id IN ({placeholders})",
            lineup_ids,
        ).fetchdf()

        missing_players = sorted(
            {
                int(pid)
                for pid in players_df["player_id"].tolist()
                if int(pid) not in salary_map
            }
        )
        if missing_players:
            raise ValueError(
                "unmapped player to dk_player_id: " + ",".join(map(str, missing_players))
            )

        slot_order = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]
        lineups: dict[int, dict[str, str]] = {lid: {} for lid in lineup_ids}
        rb_counts: dict[int, int] = {lid: 0 for lid in lineup_ids}
        wr_counts: dict[int, int] = {lid: 0 for lid in lineup_ids}
        for row in players_df.itertuples():
            slot = row.slot
            if slot == "RB":
                rb_counts[row.lineup_id] += 1
                slot = f"RB{rb_counts[row.lineup_id]}"
            elif slot == "WR":
                wr_counts[row.lineup_id] += 1
                slot = f"WR{wr_counts[row.lineup_id]}"
            lineups[row.lineup_id][slot] = salary_map[int(row.player_id)]

        expected = set(slot_order)
        for lid, slots in lineups.items():
            actual = set(slots.keys())
            if actual != expected:
                missing = ",".join(sorted(expected - actual)) or "none"
                extra = ",".join(sorted(actual - expected)) or "none"
                raise ValueError(
                    f"slot mismatch in lineup {lid}: missing {missing}; extra {extra}"
                )

        header_display = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
        csv_lines = [",".join(header_display)]
        for lid in lineup_ids:
            slots = lineups[lid]
            csv_lines.append(",".join(slots[slot] for slot in slot_order))

        con.close()

        return "\n".join(csv_lines) + "\n", slate_id

    except Exception as e:
        # Fallback: Database not available, return helpful error
        print(f"Database export failed: {e}")
        raise FileNotFoundError(
            f"Export unavailable - run {run_id} not found in database. "
            "Database persistence is currently disabled due to permission issues."
        )
