"""
Main application module for fantasy football lineup generator.
"""

import streamlit as st
from typing import Dict, Optional
import pandas as pd

# Set page config at the very top, before any other Streamlit commands
st.set_page_config(
    page_title="Fantasy Football Lineup Generator",
    page_icon="🏈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Set max width of main content
st.markdown("""
    <style>
    .main .block-container {
        max-width: 1000px;
        padding-top: 2rem;
        padding-right: 1rem;
        padding-left: 1rem;
        padding-bottom: 3rem;
    }
    </style>
""", unsafe_allow_html=True)

from config import Config
from data import FantasyDataManager
from optimizer import LineupOptimizer
from analysis import FantasyAnalyzer
from agents import FantasyAgentSystem
from display import FantasyDisplayManager

class FantasyFootballApp:
    """Main application class."""
    
    def __init__(self):
        """Initialize application components."""
        self.config = Config()
        self.config.validate()
        
        # Initialize session state
        if 'initialized' not in st.session_state:
            st.session_state.initialized = False
            st.session_state.strategy_insights = None
            st.session_state.analysis_results = None
        
        # Initialize components
        self.data_manager = FantasyDataManager()
        self.display_manager = FantasyDisplayManager()
        self.agent_system = FantasyAgentSystem()
        
        # Load data and initialize analysis/optimization components
        try:
            self.data = self.data_manager.load_data(self.config.data_path)
            self.analyzer = FantasyAnalyzer(self.data)
            self.optimizer = LineupOptimizer(self.data)
            st.session_state.initialized = True
        except Exception as e:
            st.error(f"Error initializing application: {str(e)}")
            return

    def run(self):
        """Run the application."""
        if not st.session_state.initialized:
            st.error("Application not properly initialized. Please check the data and configuration.")
            return
        
        # Display header
        self.display_manager.show_header()
        
        # Show strategy analysis
        with st.expander("📊 Strategy Analysis", expanded=True):
            if st.button("Generate Strategy Analysis") or st.session_state.strategy_insights is None:
                with st.spinner("Analyzing slate..."):
                    # First get analysis results
                    analysis_results = self.analyzer.analyze_all()
                    st.session_state.analysis_results = analysis_results
                    
                    # Generate insights from results
                    strategy_insights = self.analyzer.generate_lineup_strategy(analysis_results)
                    st.session_state.strategy_insights = strategy_insights
                    
                    # Apply strategy to optimizer
                    self.optimizer.apply_strategy_adjustments(analysis_results)
                
                if st.session_state.strategy_insights:
                    st.markdown(st.session_state.strategy_insights)
        
        # Get user input
        user_input, num_lineups, max_exposure = self.display_manager.get_user_input()
        
        # Generate lineups button
        if st.button('Generate Lineup(s)'):
            self._generate_lineups(user_input, num_lineups, max_exposure)
        
        # Reset button
        if st.button('Reset'):
            self._reset_app()
            st.experimental_rerun()

    def _generate_lineups(self, user_input: str, num_lineups: int, max_exposure: float):
        """Generate lineups based on user input."""
        try:
            # Process user input
            constraints = self.agent_system.process_user_input(user_input)
            constraints.update({
                'num_lineups': num_lineups,
                'max_exposure': max_exposure
            })
            
            # Generate lineups
            with st.spinner("Generating optimized lineups..."):
                lineups = self.optimizer.generate_lineups(constraints)
            
            if not lineups:
                st.error("No valid lineups could be generated with the given constraints.")
                return
            
            # Display lineups
            for idx, lineup in enumerate(lineups):
                self.display_manager.display_lineup(
                    lineup, 
                    idx,
                    st.session_state.analysis_results
                )
            
            # Display exposure information
            self.display_manager.display_player_exposure(self.optimizer, num_lineups)
            
        except Exception as e:
            st.error(f"Error generating lineups: {str(e)}")

    def _reset_app(self):
        """Reset application state."""
        self.optimizer.previous_lineups = []
        self.optimizer.player_usage = {}
        st.session_state.clear()
        st.session_state.initialized = False

def main():
    """Application entry point."""
    app = FantasyFootballApp()
    app.run()

if __name__ == "__main__":
    main()