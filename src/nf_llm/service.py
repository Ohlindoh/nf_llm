# src/nf_llm/service.py
"""
Thin service layer that the API (or any other client) can call.
Keeps LineupOptimizer details out of the HTTP layer.
"""

from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

from nf_llm.optimizer import LineupOptimizer


def build_lineups(
    csv_path: str,
    slate_id: str,
    constraints: Dict[str, Any],
) -> List[Dict]:
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

    # --- 2. Run optimiser ---
    opt = LineupOptimizer(df)
    lineups = opt.generate_lineups(constraints=constraints)

    # --- 3. Return plain Python objects (already JSON‑safe) ---
    return lineups
