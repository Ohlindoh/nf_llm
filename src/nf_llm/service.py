# src/nf_llm/service.py
"""
Thin service layer that the API (or any other client) can call.
Keeps LineupOptimizer details out of the HTTP layer.
"""

from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import traceback, logging

from nf_llm.data_io import preprocess_data
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
    df = preprocess_data(df)

    # --- 2. Run optimiser ---
    opt = LineupOptimizer(df)
    lineups = opt.generate_lineups(constraints=constraints)

    # --- 3. Return plain Python objects (already JSON‑safe) ---
    return lineups


def get_undervalued_players_data(csv_path: str, top_n: int = 5) -> Dict[str, List[Dict]]:
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
    for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
        position_data = df[df['player_position_id'] == position].sort_values('value', ascending=False)
        # Convert to list of dicts for JSON serialization
        players_list = position_data.head(top_n)[['player_name', 'team', 'salary', 'projected_points', 'value']].to_dict('records')
        undervalued[position] = players_list
    
    return undervalued
