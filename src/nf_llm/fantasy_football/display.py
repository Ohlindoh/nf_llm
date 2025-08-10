"""
Display module for fantasy football lineup generator.
Handles all Streamlit UI components and visualization.
"""

import streamlit as st
from typing import Dict, List, Optional
import pandas as pd
from dataclasses import dataclass

@dataclass
class DisplayConfig:
    """Configuration for display formatting."""
    POSITION_ORDER: List[str] = None
    DEFAULT_NUM_LINEUPS: int = 1
    DEFAULT_MAX_EXPOSURE: float = 0.3
    
    def __post_init__(self):
        if self.POSITION_ORDER is None:
            self.POSITION_ORDER = ['QB', 'RB1', 'RB2', 'WR1', 'WR2', 'WR3', 'TE', 'FLEX', 'DST']

class FantasyDisplayManager:
    """Manages Streamlit UI components and display formatting."""
    
    def __init__(self, config: Optional[DisplayConfig] = None):
        self.config = config or DisplayConfig()
        if 'strategy_insights' not in st.session_state:
            st.session_state.strategy_insights = None

    def show_header(self):
        """Display application header."""
        st.title('Daily Fantasy Football Lineup Generator')

    def show_strategy_section(self, analyzer) -> Optional[str]:
        """Display strategy analysis section."""
        with st.expander("📊 View Strategy Analysis", expanded=True):
            st.subheader("Current Slate Analysis")
            if st.button("Generate Strategy Analysis"):
                with st.spinner("Analyzing slate..."):
                    strategy_insights = analyzer.generate_lineup_strategy()
                    st.session_state.strategy_insights = strategy_insights
                    st.markdown(strategy_insights)
            elif st.session_state.strategy_insights:
                st.markdown(st.session_state.strategy_insights)
        return st.session_state.strategy_insights

    def show_value_analysis(self, analyzer):
        """Display detailed value analysis section."""
        with st.expander("💰 View Value Analysis", expanded=False):
            if st.button("Show Value Analysis"):
                analysis = analyzer.analyze_all()
                
                # Display Value Plays
                st.subheader("Value Plays by Position")
                for position, plays in analysis['value_plays'].items():
                    if not plays.empty:
                        st.write(f"**{position}**")
                        formatted_plays = plays.copy()
                        formatted_plays['salary'] = formatted_plays['salary'].apply(lambda x: f"${x:,.0f}")
                        formatted_plays['points_per_dollar'] = formatted_plays['points_per_dollar'].apply(lambda x: f"{x:.2f}")
                        formatted_plays['points_zscore'] = formatted_plays['points_zscore'].apply(lambda x: f"{x:.2f}")
                        st.dataframe(formatted_plays)
                
                # Display Stack Analysis
                st.subheader("Top Stacking Opportunities")
                if analysis['stacks']:
                    stacks_df = pd.DataFrame(analysis['stacks'])
                    formatted_stacks = stacks_df.copy()
                    formatted_stacks['total_salary'] = formatted_stacks['total_salary'].apply(lambda x: f"${x:,.0f}")
                    formatted_stacks['stack_value'] = formatted_stacks['stack_value'].apply(lambda x: f"{x:.2f}")
                    st.dataframe(formatted_stacks)

    def get_user_input(self) -> tuple:
        """Get user input for lineup generation."""
        user_input = st.text_area(
            'Enter your lineup requests:',
            placeholder="Example: I want Patrick Mahomes and Travis Kelce, no Jets players",
            height=75
        )
        
        col1, col2 = st.columns(2)
        with col1:
            num_lineups = st.number_input(
                'Number of Lineups',
                min_value=1,
                max_value=150,
                value=self.config.DEFAULT_NUM_LINEUPS
            )
        with col2:
            max_exposure = st.slider(
                'Maximum Player Exposure (%)',
                min_value=0,
                max_value=100,
                value=int(self.config.DEFAULT_MAX_EXPOSURE * 100)
            ) / 100.0
            
        return user_input, num_lineups, max_exposure

    def display_lineup(self, lineup: Dict, idx: Optional[int] = None,
                      analysis_results: Optional[Dict] = None):
        """Display a single lineup with analysis."""
        if idx is not None:
            st.subheader(f'Lineup {idx + 1}')
        
        if 'error' in lineup:
            st.error(lineup['error'])
            return
        
        # Prepare lineup data
        lineup_data = []
        total_salary = 0
        total_projected_points = 0
        
        for position in self.config.POSITION_ORDER:
            player = lineup.get(position)
            if player:
                salary = float(player['salary'])
                projected_points = float(player['projected_points'])
                lineup_data.append({
                    'Position': position,
                    'Player': player['player_name'],
                    'Team': player['team'].upper(),
                    'Projected': f"{projected_points:.1f}",
                    'Salary': f"${salary:,.0f}"
                })
                total_salary += salary
                total_projected_points += projected_points
            else:
                lineup_data.append({
                    'Position': position,
                    'Player': '',
                    'Team': '',
                    'Projected': '',
                    'Salary': ''
                })
        
        # Display lineup table
        df = pd.DataFrame(lineup_data)
        st.table(df)
        
        # Display totals
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Salary", f"${total_salary:,.0f}")
        with col2:
            st.metric("Projected Points", f"{total_projected_points:.2f}")
        
        # Display analysis if available
        if analysis_results:
            self._display_lineup_analysis(lineup, analysis_results)

    def _display_lineup_analysis(self, lineup: Dict, analysis_results: Dict):
        """Display detailed analysis for a lineup."""
        with st.expander("👓 View Lineup Analysis", expanded=False):
            # Check for value plays
            value_players = []
            if 'value_plays' in analysis_results:
                for pos, plays in analysis_results['value_plays'].items():
                    for _, player in plays.iterrows():
                        if any(p['player_name'] == player['player_name'] for p in lineup.values()):
                            value_players.append(
                                f"- {player['player_name']}: {player['points_per_dollar']:.2f} pts/$K"
                            )
            
            if value_players:
                st.write("**Value Plays:**")
                st.markdown("\n".join(value_players))
            
            # Check for stacks
            team_counts = {}
            for player in lineup.values():
                team_counts[player['team']] = team_counts.get(player['team'], 0) + 1
            
            stacks = [team for team, count in team_counts.items() if count >= 2]
            if stacks:
                st.write("**Stacks:**")
                for team in stacks:
                    stack_players = [
                        p['player_name'] for p in lineup.values() 
                        if p['team'] == team
                    ]
                    st.markdown(f"- {team.upper()}: {', '.join(stack_players)}")

    def display_player_exposure(self, optimizer, num_lineups: int):
        """Display player exposure statistics."""
        st.subheader('Player Exposure')
        
        exposure_data = []
        for player_name, count in optimizer.player_usage.items():
            avg_projected_points = optimizer.get_average_projected_points(player_name)
            exposure_data.append({
                'Player': player_name,
                'Lineups Used': count,
                'Exposure (%)': f"{(count / num_lineups * 100):.1f}%",
                'Avg Projected': f"{avg_projected_points:.1f}"
            })
        
        if exposure_data:
            exposure_df = pd.DataFrame(exposure_data)
            exposure_df = exposure_df.sort_values('Lineups Used', ascending=False)
            st.table(exposure_df)
        else:
            st.write("No exposure data available yet.")

    def show_optimization_progress(self, current: int, total: int):
        """Display optimization progress."""
        progress_bar = st.progress(0)
        progress_text = st.empty()
        
        progress = current / total
        progress_bar.progress(progress)
        progress_text.text(f'Generating lineup {current} of {total}...')
        
        if current == total:
            progress_text.text('All lineups generated!')

    def show_error(self, message: str):
        """Display error message."""
        st.error(message)

    def show_warning(self, message: str):
        """Display warning message."""
        st.warning(message)

    def show_success(self, message: str):
        """Display success message."""
        st.success(message)