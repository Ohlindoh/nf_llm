"""
Analysis module for fantasy football data.
Handles value analysis, stack analysis, and strategy generation.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

@dataclass
class AnalysisSettings:
    """Settings for analysis calculations."""
    VALUE_Z_SCORE_THRESHOLD: float = 1.0
    STACK_SALARY_CAP: int = 15000  # 30% of total salary cap
    CORRELATION_BONUS: float = 0.1  # 10% bonus for correlated players
    MIN_VALUE_SCORE: float = 1.5  # Minimum points per $1000
    TOP_N_RESULTS: int = 5

class FantasyAnalyzer:
    """Analyzes fantasy football data for insights and strategy."""
    
    def __init__(self, data: pd.DataFrame, settings: Optional[AnalysisSettings] = None):
        self.data = data
        self.settings = settings or AnalysisSettings()
        self._validate_data()

    def _validate_data(self):
        """Ensure data has required columns and correct types."""
        required_columns = {'player_name', 'player_position_id', 'team', 
                          'salary', 'projected_points', 'rank_ecr'}
        missing = required_columns - set(self.data.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Ensure numeric types
        numeric_columns = {'salary', 'projected_points', 'rank_ecr'}
        for col in numeric_columns:
            self.data[col] = pd.to_numeric(self.data[col], errors='coerce')

    # analysis.py
    def analyze_all(self) -> Dict:
        """Run all analyses and return compiled results."""
        try:
            results = {
                'value_plays': {},
                'stacks': [],
                'inefficiencies': {}
            }
            
            try:
                value_plays = self.analyze_value_plays()
                results['value_plays'] = value_plays
            except Exception as e:
                print(f"Error in value plays analysis: {str(e)}")
            
            try:
                stacks = self.analyze_stacks()
                if isinstance(stacks, list):
                    results['stacks'] = stacks
            except Exception as e:
                print(f"Error in stacks analysis: {str(e)}")
            
            try:
                inefficiencies = self.analyze_market_inefficiencies()
                if isinstance(inefficiencies, dict):
                    results['inefficiencies'] = inefficiencies
            except Exception as e:
                print(f"Error in inefficiencies analysis: {str(e)}")
            
            return results
        
        except Exception as e:
            print(f"Error in analyze_all: {str(e)}")
            return {
                'value_plays': {},
                'stacks': [],
                'inefficiencies': {}
            }

    # analysis.py
    def analyze_value_plays(self) -> Dict[str, List[Dict]]:
        """Identify value plays by position."""
        value_plays = {}
        
        for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
            pos_data = self.data[self.data['player_position_id'] == position].copy()
            if not pos_data.empty:
                # Calculate basic value metrics
                pos_data['points_per_dollar'] = pos_data['projected_points'] / (pos_data['salary'] / 1000)
                pos_data['value_score'] = pos_data['points_per_dollar']
                
                # Calculate z-scores
                pos_data['points_zscore'] = (
                    (pos_data['projected_points'] - pos_data['projected_points'].mean()) 
                    / pos_data['projected_points'].std()
                )
                
                # Calculate rank value
                pos_data['salary_rank'] = pos_data['salary'].rank(ascending=False)
                pos_data['rank_value'] = pos_data['salary_rank'] - pos_data['rank_ecr']
                
                # Convert qualifying rows to list of dictionaries
                qualified_plays = pos_data[
                    (pos_data['points_zscore'] > self.settings.VALUE_Z_SCORE_THRESHOLD) |
                    (pos_data['points_per_dollar'] > self.settings.MIN_VALUE_SCORE)
                ].to_dict('records')
                
                value_plays[position] = qualified_plays
                
        return value_plays

    def analyze_stacks(self) -> List[Dict]:
        """Identify optimal stacking opportunities."""
        qb_data = self.data[self.data['player_position_id'] == 'QB']
        receiver_data = self.data[self.data['player_position_id'].isin(['WR', 'TE'])]
        
        stacks = []
        for _, qb in qb_data.iterrows():
            team_receivers = receiver_data[receiver_data['team'] == qb['team']]
            
            for _, receiver in team_receivers.iterrows():
                combined_salary = qb['salary'] + receiver['salary']
                if combined_salary <= self.settings.STACK_SALARY_CAP:
                    # Calculate stack metrics
                    correlation_bonus = receiver['projected_points'] * self.settings.CORRELATION_BONUS
                    stack_projection = qb['projected_points'] + receiver['projected_points'] + correlation_bonus
                    stack_value = stack_projection / (combined_salary / 1000)
                    
                    stacks.append({
                        'qb': qb['player_name'],
                        'qb_salary': qb['salary'],
                        'receiver': receiver['player_name'],
                        'receiver_salary': receiver['salary'],
                        'team': qb['team'],
                        'total_salary': combined_salary,
                        'projected_points': stack_projection,
                        'stack_value': stack_value
                    })
        
        # Sort by stack value and return top results
        return sorted(stacks, key=lambda x: x['stack_value'], reverse=True)[:self.settings.TOP_N_RESULTS]

    def analyze_market_inefficiencies(self) -> Dict[str, pd.DataFrame]:
        """Identify market inefficiencies by position."""
        inefficiencies = {}
        
        for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
            pos_data = self.data[self.data['player_position_id'] == position].copy()
            if not pos_data.empty:
                # Calculate expected points based on salary
                pos_data['salary_percentile'] = pos_data['salary'].rank(pct=True)
                coefficients = np.polyfit(pos_data['salary_percentile'], 
                                        pos_data['projected_points'], 1)
                pos_data['expected_points'] = np.polyval(coefficients, 
                                                       pos_data['salary_percentile'])
                
                # Calculate inefficiency metrics
                pos_data['points_vs_expected'] = (pos_data['projected_points'] - 
                                                pos_data['expected_points'])
                pos_data['inefficiency_score'] = (pos_data['points_vs_expected'] / 
                                                pos_data['expected_points'])
                
                inefficiencies[position] = pos_data[
                    pos_data['points_vs_expected'] > 0
                ].nlargest(
                    self.settings.TOP_N_RESULTS,
                    'inefficiency_score'
                )[['player_name', 'team', 'salary', 'projected_points', 
                   'expected_points', 'points_vs_expected', 'inefficiency_score']]
        
        return inefficiencies

    def generate_lineup_strategy(self, analysis_results: Optional[Dict] = None) -> str:
        """Generate strategic insights and recommendations."""
        if analysis_results is None:
            analysis_results = self.analyze_all()
        
        insights = []
        
        # Value Plays Summary
        insights.append("🎯 TOP VALUE PLAYS BY POSITION:")
        for position, plays in analysis_results['value_plays'].items():
            if plays:  # plays is now a list
                insights.append(f"\n{position} Standouts:")
                for play in plays[:3]:  # Take first 3 plays
                    insights.append(
                        f"- {play['player_name']}: ${play['salary']:,} | "
                        f"{play['projected_points']:.1f} pts | "
                        f"Value: {play['points_per_dollar']:.2f} pts/$K"
                    )
        
        
        # Stack Analysis
        insights.append("\n\n🔄 OPTIMAL STACKING OPPORTUNITIES:")
        if isinstance(analysis_results['stacks'], list):  # Type check for stacks
            for stack in analysis_results['stacks'][:3]:
                insights.append(
                    f"- {stack['team'].upper()}: {stack['qb']} + {stack['receiver']}\n"
                    f"  Combined: ${stack['total_salary']:,} | "
                    f"Proj: {stack['projected_points']:.1f} pts"
                )
        
        # Market Inefficiencies
        insights.append("\n\n💰 MARKET INEFFICIENCIES:")
        for position, players in analysis_results['inefficiencies'].items():
            if isinstance(players, pd.DataFrame) and not players.empty:
                for _, player in players.head(2).iterrows():
                    insights.append(
                        f"- {player['player_name']} ({position}): "
                        f"+{player['points_vs_expected']:.1f} pts vs. expected"
                    )
        
        # Building Strategy
        insights.append("\n\n🎮 LINEUP BUILDING STRATEGY:")
        insights.append("1. Consider starting with a top QB stack")
        insights.append("2. Mix high-floor value plays with proven performers")
        insights.append("3. Target salary-based inefficiencies in FLEX")
        insights.append("4. Leverage correlations in game stacks")
        
        return "\n".join(insights)

    def get_player_analysis(self, player_name: str) -> Dict:
        """Get detailed analysis for a specific player."""
        player_data = self.data[self.data['player_name'] == player_name]
        if player_data.empty:
            return {'error': 'Player not found'}
        
        player = player_data.iloc[0]
        position_data = self.data[self.data['player_position_id'] == player['player_position_id']]
        
        return {
            'name': player['player_name'],
            'position': player['player_position_id'],
            'team': player['team'],
            'salary': player['salary'],
            'projected_points': player['projected_points'],
            'value_score': player['projected_points'] / (player['salary'] / 1000),
            'position_rank': position_data['projected_points'].rank(ascending=False)[player_data.index[0]],
            'salary_rank': position_data['salary'].rank(ascending=False)[player_data.index[0]],
            'zscore': (player['projected_points'] - position_data['projected_points'].mean()) / position_data['projected_points'].std()
        }