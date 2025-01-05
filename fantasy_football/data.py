"""
Data module for fantasy football lineup generator.
Handles data loading, preprocessing, and validation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import pandas as pd
import numpy as np
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DataConfig:
    """Configuration for data processing."""
    REQUIRED_COLUMNS: Set[str] = field(default_factory=lambda: {
        'player_name', 'player_position_id', 'team', 
        'salary', 'projected_points', 'rank_ecr'
    })
    VALID_POSITIONS: Set[str] = field(default_factory=lambda: {
        'QB', 'RB', 'WR', 'TE', 'DST'
    })
    MIN_SALARY: int = 2000
    MAX_SALARY: int = 15000
    MIN_PLAYERS_PER_POSITION: Dict[str, int] = field(default_factory=lambda: {
        'QB': 10, 'RB': 20, 'WR': 20, 'TE': 10, 'DST': 8
    })

class FantasyDataManager:
    """Manages fantasy football data loading and preprocessing."""
    
    def __init__(self, config: Optional[DataConfig] = None):
        self.config = config or DataConfig()
        self.data = None
        self.validation_errors = []

    def load_data(self, file_path: str) -> pd.DataFrame:
        """Load and preprocess fantasy football data."""
        try:
            logger.info(f"Loading data from {file_path}")
            self.data = pd.read_csv(file_path)
            self._preprocess_data()
            if self._validate_data():
                logger.info("Data loaded and validated successfully")
                return self.data
            else:
                error_msg = "\n".join(self.validation_errors)
                logger.error(f"Data validation failed:\n{error_msg}")
                raise ValueError(f"Data validation failed:\n{error_msg}")
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            raise

    def _preprocess_data(self):
        """Preprocess the fantasy football data."""
        try:
            # Clean player names
            self.data['player_name'] = (self.data['player_name']
                                      .str.replace(' ', '')
                                      .str.lower())
            
            # Clean team names
            if 'player_team_id' in self.data.columns:
                self.data = self.data.rename(columns={'player_team_id': 'team'})
            self.data['team'] = self.data['team'].str.lower()
            
            # Convert salary and points to numeric
            self.data['salary'] = pd.to_numeric(
                self.data['salary'].replace('[\$,]', '', regex=True),
                errors='coerce'
            )
            self.data['projected_points'] = pd.to_numeric(
                self.data['projected_points'],
                errors='coerce'
            )
            self.data['rank_ecr'] = pd.to_numeric(
                self.data['rank_ecr'],
                errors='coerce'
            )
            
            # Remove rows with NaN values in critical columns
            self.data = self.data.dropna(subset=[
                'player_name', 'team', 'salary', 'projected_points'
            ])
            
            # Calculate basic value metrics
            self.data['value'] = self.data['projected_points'] / self.data['salary']
            
            logger.info("Data preprocessing completed successfully")
            
        except Exception as e:
            logger.error(f"Error preprocessing data: {str(e)}")
            raise

    def _validate_data(self) -> bool:
        """Validate the preprocessed data."""
        self.validation_errors = []
        
        # Check required columns
        missing_columns = self.config.REQUIRED_COLUMNS - set(self.data.columns)
        if missing_columns:
            self.validation_errors.append(
                f"Missing required columns: {missing_columns}"
            )
        
        # Check position values
        invalid_positions = set(self.data['player_position_id'].unique()) - self.config.VALID_POSITIONS
        if invalid_positions:
            self.validation_errors.append(
                f"Invalid positions found: {invalid_positions}"
            )
        
        # Check salary ranges
        salary_issues = self.data[
            (self.data['salary'] < self.config.MIN_SALARY) |
            (self.data['salary'] > self.config.MAX_SALARY)
        ]
        if not salary_issues.empty:
            self.validation_errors.append(
                f"Found {len(salary_issues)} players with invalid salaries"
            )
        
        # Check minimum players per position
        for position, min_count in self.config.MIN_PLAYERS_PER_POSITION.items():
            position_count = len(self.data[self.data['player_position_id'] == position])
            if position_count < min_count:
                self.validation_errors.append(
                    f"Insufficient {position} players: {position_count}/{min_count}"
                )
        
        return len(self.validation_errors) == 0

    def get_position_data(self, position: str) -> pd.DataFrame:
        """Get data for a specific position."""
        if position not in self.config.VALID_POSITIONS:
            raise ValueError(f"Invalid position: {position}")
        return self.data[self.data['player_position_id'] == position].copy()

    def get_player_data(self, player_name: str) -> Optional[pd.Series]:
        """Get data for a specific player."""
        player_data = self.data[self.data['player_name'] == player_name.lower().replace(' ', '')]
        return player_data.iloc[0] if not player_data.empty else None

    def get_team_data(self, team: str) -> pd.DataFrame:
        """Get data for all players from a specific team."""
        return self.data[self.data['team'] == team.lower()].copy()

    def get_value_plays(self, threshold: float = 2.0) -> pd.DataFrame:
        """Get players exceeding the value threshold."""
        return self.data[self.data['value'] > threshold].copy()

    def get_salary_range(self, position: str) -> Dict[str, float]:
        """Get salary statistics for a position."""
        pos_data = self.get_position_data(position)
        return {
            'min': pos_data['salary'].min(),
            'max': pos_data['salary'].max(),
            'mean': pos_data['salary'].mean(),
            'median': pos_data['salary'].median()
        }

    def get_correlation_matrix(self, team: str) -> pd.DataFrame:
        """Get correlation matrix for players on a team."""
        team_data = self.get_team_data(team)
        
        # Create correlation matrix using projected points
        players = team_data['player_name'].unique()
        corr_matrix = pd.DataFrame(index=players, columns=players)
        
        # Fill correlation matrix based on position relationships
        for i, player1 in enumerate(players):
            for j, player2 in enumerate(players):
                if i == j:
                    corr_matrix.loc[player1, player2] = 1.0
                else:
                    pos1 = team_data[team_data['player_name'] == player1]['player_position_id'].iloc[0]
                    pos2 = team_data[team_data['player_name'] == player2]['player_position_id'].iloc[0]
                    
                    # Define correlation based on position relationships
                    if pos1 == 'QB' and pos2 in ['WR', 'TE']:
                        corr_matrix.loc[player1, player2] = 0.6
                    elif pos1 in ['WR', 'TE'] and pos2 == 'QB':
                        corr_matrix.loc[player1, player2] = 0.6
                    elif pos1 == pos2:
                        corr_matrix.loc[player1, player2] = -0.1  # Slight negative correlation
                    else:
                        corr_matrix.loc[player1, player2] = 0.1  # Slight positive correlation
        
        return corr_matrix

    def save_processed_data(self, file_path: str):
        """Save processed data to a new CSV file."""
        if self.data is not None:
            output_path = Path(file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.data.to_csv(output_path, index=False)
            logger.info(f"Processed data saved to {output_path}")
        else:
            logger.error("No data to save")

    def get_data_summary(self) -> Dict:
        """Get summary statistics of the data."""
        if self.data is None:
            return {}
        
        return {
            'total_players': len(self.data),
            'players_by_position': self.data['player_position_id'].value_counts().to_dict(),
            'salary_stats': {
                'min': self.data['salary'].min(),
                'max': self.data['salary'].max(),
                'mean': self.data['salary'].mean(),
                'median': self.data['salary'].median()
            },
            'points_stats': {
                'min': self.data['projected_points'].min(),
                'max': self.data['projected_points'].max(),
                'mean': self.data['projected_points'].mean(),
                'median': self.data['projected_points'].median()
            },
            'teams_represented': self.data['team'].nunique(),
            'value_plays_count': len(self.get_value_plays())
        }