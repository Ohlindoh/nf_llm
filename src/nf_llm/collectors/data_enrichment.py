"""
Data enrichment module to add floor, ceiling, variance, and ownership data.
Calculates real statistical metrics based on historical performance.
"""

import pandas as pd
import numpy as np
from typing import Optional


def calculate_player_volatility_metrics(
    historical_data: pd.DataFrame,
    current_projections: pd.DataFrame,
    games_back: int = 5
) -> pd.DataFrame:
    """
    Calculate floor, ceiling, and variance based on recent performance.
    
    Args:
        historical_data: DataFrame with columns [player_name, week, actual_points]
        current_projections: Current week's projections
        games_back: Number of recent games to analyze
    
    Returns:
        DataFrame with added floor, ceiling, variance columns
    """
    enriched = current_projections.copy()
    
    # Group historical data by player
    player_stats = {}
    for player in historical_data['player_name'].unique():
        player_games = historical_data[
            historical_data['player_name'] == player
        ].tail(games_back)
        
        if len(player_games) >= 3:  # Need minimum games for statistics
            points = player_games['actual_points'].values
            player_stats[player] = {
                'floor': np.percentile(points, 20),  # 20th percentile
                'ceiling': np.percentile(points, 80),  # 80th percentile
                'median': np.median(points),
                'std_dev': np.std(points),
                'consistency': 1 - (np.std(points) / (np.mean(points) + 0.1))  # Avoid div by zero
            }
    
    # Apply calculated metrics to projections
    for idx, row in enriched.iterrows():
        player = row['player_name']
        if player in player_stats:
            stats = player_stats[player]
            enriched.at[idx, 'floor'] = stats['floor']
            enriched.at[idx, 'ceiling'] = stats['ceiling']
            enriched.at[idx, 'variance'] = stats['std_dev']
            enriched.at[idx, 'consistency_score'] = stats['consistency']
        else:
            # Default values for players without history
            proj = row['projected_points']
            # Use position-based defaults
            if row['player_position_id'] == 'QB':
                enriched.at[idx, 'floor'] = proj * 0.75
                enriched.at[idx, 'ceiling'] = proj * 1.25
                enriched.at[idx, 'variance'] = proj * 0.15
            elif row['player_position_id'] in ['RB', 'WR']:
                enriched.at[idx, 'floor'] = proj * 0.6
                enriched.at[idx, 'ceiling'] = proj * 1.4
                enriched.at[idx, 'variance'] = proj * 0.25
            else:  # TE, DST, K
                enriched.at[idx, 'floor'] = proj * 0.7
                enriched.at[idx, 'ceiling'] = proj * 1.3
                enriched.at[idx, 'variance'] = proj * 0.20
            enriched.at[idx, 'consistency_score'] = 0.5  # Neutral
    
    return enriched


def add_ownership_projections(
    data: pd.DataFrame,
    slate_info: Optional[dict] = None
) -> pd.DataFrame:
    """
    Add ownership percentage projections based on various factors.
    
    Simple heuristic: Higher salary + higher projection = higher ownership
    """
    enriched = data.copy()
    
    # Normalize salary and projections to 0-1 scale
    enriched['salary_norm'] = (
        enriched['salary'] - enriched['salary'].min()
    ) / (enriched['salary'].max() - enriched['salary'].min())
    
    enriched['proj_norm'] = (
        enriched['projected_points'] - enriched['projected_points'].min()
    ) / (enriched['projected_points'].max() - enriched['projected_points'].min())
    
    # Calculate value score (points per $1000)
    enriched['value_score'] = enriched['projected_points'] / (enriched['salary'] / 1000)
    enriched['value_norm'] = (
        enriched['value_score'] - enriched['value_score'].min()
    ) / (enriched['value_score'].max() - enriched['value_score'].min())
    
    # Estimate ownership based on value and name recognition
    # High value + reasonable salary = high ownership
    enriched['ownership_projection'] = (
        enriched['value_norm'] * 0.5 +  # Value drives ownership
        enriched['proj_norm'] * 0.3 +   # High projections attract
        (1 - enriched['salary_norm']) * 0.2  # Cheaper players get more play
    ) * 40  # Scale to 0-40% range
    
    # Adjust by position (QBs and top RBs typically higher owned)
    position_multipliers = {
        'QB': 1.2,
        'RB': 1.1,
        'WR': 1.0,
        'TE': 0.9,
        'DST': 0.8,
        'K': 0.7
    }
    
    for pos, mult in position_multipliers.items():
        mask = enriched['player_position_id'] == pos
        enriched.loc[mask, 'ownership_projection'] *= mult
    
    # Cap ownership at reasonable levels
    enriched['ownership_projection'] = enriched['ownership_projection'].clip(1, 50)
    
    # Clean up temporary columns
    enriched = enriched.drop(columns=['salary_norm', 'proj_norm', 'value_norm'])
    
    return enriched


def identify_game_stacks(data: pd.DataFrame) -> pd.DataFrame:
    """
    Identify correlated plays for stacking strategies.
    """
    enriched = data.copy()
    
    # Create game stacking correlation scores
    enriched['stack_eligible'] = enriched['player_position_id'].isin(['QB', 'WR', 'TE'])
    
    # For each team, identify the primary stacking QB
    team_qbs = enriched[enriched['player_position_id'] == 'QB'].groupby('team_abbreviation')
    enriched['is_primary_qb'] = False
    
    for team, qbs in team_qbs:
        if len(qbs) > 0:
            # Highest projected QB is primary
            primary_qb_idx = qbs['projected_points'].idxmax()
            enriched.at[primary_qb_idx, 'is_primary_qb'] = True
    
    return enriched


def enrich_fantasy_data(csv_path: str, output_path: str = None) -> pd.DataFrame:
    """
    Main enrichment function to add all strategic columns.
    """
    # Load current data
    data = pd.read_csv(csv_path)
    
    # Add synthetic historical performance (in production, load real historical data)
    # For now, create reasonable floor/ceiling based on position and projection
    enriched = data.copy()
    
    # Position-specific volatility profiles
    position_profiles = {
        'QB': {'floor_mult': 0.75, 'ceiling_mult': 1.25, 'consistency': 0.7},
        'RB': {'floor_mult': 0.5, 'ceiling_mult': 1.5, 'consistency': 0.5},
        'WR': {'floor_mult': 0.4, 'ceiling_mult': 1.6, 'consistency': 0.4},
        'TE': {'floor_mult': 0.3, 'ceiling_mult': 1.4, 'consistency': 0.6},
        'DST': {'floor_mult': 0.6, 'ceiling_mult': 1.3, 'consistency': 0.65},
        'K': {'floor_mult': 0.7, 'ceiling_mult': 1.2, 'consistency': 0.75},
    }
    
    for pos, profile in position_profiles.items():
        mask = enriched['player_position_id'] == pos
        enriched.loc[mask, 'floor'] = (
            enriched.loc[mask, 'projected_points'] * profile['floor_mult']
        )
        enriched.loc[mask, 'ceiling'] = (
            enriched.loc[mask, 'projected_points'] * profile['ceiling_mult']
        )
        enriched.loc[mask, 'consistency_score'] = profile['consistency']
    
    # Calculate variance as standard deviation estimate
    enriched['variance'] = (enriched['ceiling'] - enriched['floor']) / 4
    
    # Add ownership projections
    enriched = add_ownership_projections(enriched)
    
    # Add stacking information
    enriched = identify_game_stacks(enriched)
    
    # Save enriched data
    if output_path:
        enriched.to_csv(output_path, index=False)
    
    return enriched


if __name__ == "__main__":
    # Example usage
    input_csv = "data/merged_fantasy_football_data.csv"
    output_csv = "data/enriched_fantasy_football_data.csv"
    
    enriched_data = enrich_fantasy_data(input_csv, output_csv)
    print(f"Enriched data saved to {output_csv}")
    print(f"Added columns: floor, ceiling, variance, consistency_score, ownership_projection")
