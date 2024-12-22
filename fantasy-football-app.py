import os
import pulp
import pandas as pd
import numpy as np
import json
import streamlit as st
import autogen
import warnings
from autogen import AssistantAgent, UserProxyAgent
from typing import Dict, List, Optional, Set, Tuple, Union
from pathlib import Path

# Suppress warnings
warnings.filterwarnings('ignore')

# Load data
data_file = 'data/merged_fantasy_football_data.csv'
data = pd.read_csv(data_file)

def preprocess_data(data):
    """Preprocess the fantasy football data."""
    data['player_name'] = data['player_name'].str.replace(' ', '').str.lower()
    
    # Standardize team column name
    if 'player_team_id' in data.columns:
        data = data.rename(columns={'player_team_id': 'team'})
    
    data['team'] = data['team'].str.lower()
    data['salary'] = pd.to_numeric(data['salary'].replace('[\$,]', '', regex=True), errors='coerce')
    data['projected_points'] = pd.to_numeric(data['projected_points'], errors='coerce')
    data['rank_ecr'] = pd.to_numeric(data['rank_ecr'], errors='coerce')
    
    # Remove any rows with NaN values in critical columns
    critical_columns = ['player_name', 'team', 'salary', 'projected_points', 'rank_ecr']
    data = data.dropna(subset=critical_columns)
    
    # Calculate basic value
    data['value'] = data['projected_points'] / data['salary']
    
    return data

data = preprocess_data(data)

def analyze_data_for_strategy(data: pd.DataFrame) -> dict:
    """Analyze fantasy football data for strategic insights."""
    analysis = {}
    
    # Validate input data has required columns
    required_columns = ['player_name', 'player_position_id', 'team', 'salary', 'projected_points', 'rank_ecr']
    missing_columns = [col for col in required_columns if col not in data.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")
    
    # 1. Value Analysis
    value_plays = {}
    for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
        pos_data = data[data['player_position_id'] == position].copy()
        if not pos_data.empty:
            try:
                # Basic calculations first
                pos_data['points_per_dollar'] = pos_data['projected_points'] / pos_data['salary']
                pos_data['value_score'] = pos_data['points_per_dollar'] * 1000  # Scale for readability
                
                # Z-score calculations
                if len(pos_data) > 1:  # Need at least 2 players for z-score
                    pos_data['points_zscore'] = (pos_data['projected_points'] - pos_data['projected_points'].mean()) / pos_data['projected_points'].std()
                else:
                    pos_data['points_zscore'] = 0
                
                # Rank calculations
                pos_data['salary_rank'] = pos_data['salary'].rank(ascending=False)
                pos_data['rank_value'] = pos_data['salary_rank'] - pos_data['rank_ecr']
                
                # Identify value plays
                avg_value = pos_data['value_score'].mean()
                value_plays[position] = pos_data[
                    (pos_data['value_score'] > avg_value) |  # Better than average value
                    (pos_data['rank_value'] > 3)  # ECR at least 3 spots better than salary rank
                ][['player_name', 'salary', 'projected_points', 'value_score', 'rank_value', 'points_zscore']].sort_values('value_score', ascending=False)
            
            except Exception as e:
                print(f"Error processing {position}: {str(e)}")
                value_plays[position] = pd.DataFrame()  # Empty DataFrame for this position
    
    analysis['value_plays'] = value_plays

    # 2. Stack Analysis
    try:
        qb_data = data[data['player_position_id'] == 'QB']
        receiver_data = data[data['player_position_id'].isin(['WR', 'TE'])]
        
        stacks = []
        for _, qb in qb_data.iterrows():
            team_receivers = receiver_data[receiver_data['team'] == qb['team']]
            
            for _, receiver in team_receivers.iterrows():
                combined_salary = qb['salary'] + receiver['salary']
                if combined_salary <= 15000:  # 30% of salary cap for main stacking pieces
                    stack_projection = qb['projected_points'] + receiver['projected_points']
                    stack_value = stack_projection / (combined_salary / 1000)
                    
                    stacks.append({
                        'qb': qb['player_name'],
                        'receiver': receiver['player_name'],
                        'total_salary': combined_salary,
                        'total_projection': stack_projection,
                        'stack_value': stack_value
                    })
        
        analysis['stacks'] = sorted(stacks, key=lambda x: x['stack_value'], reverse=True)
    except Exception as e:
        print(f"Error in stack analysis: {str(e)}")
        analysis['stacks'] = []

    # 3. Market Inefficiencies Analysis
    try:
        analysis['inefficiencies'] = {}
        for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
            pos_data = data[data['player_position_id'] == position].copy()
            if not pos_data.empty:
                pos_data['salary_percentile'] = pos_data['salary'].rank(pct=True)
                pos_data['expected_points'] = pos_data['salary_percentile'] * pos_data['projected_points'].max()
                pos_data['points_vs_expected'] = pos_data['projected_points'] - pos_data['expected_points']
                
                analysis['inefficiencies'][position] = pos_data[
                    pos_data['points_vs_expected'] > 0
                ][['player_name', 'salary', 'projected_points', 'points_vs_expected']].nlargest(
                    3, 'points_vs_expected'
                )
    except Exception as e:
        print(f"Error in inefficiencies analysis: {str(e)}")
        analysis['inefficiencies'] = {}

    # 4. Tournament Plays Analysis
    try:
        analysis['tournament_plays'] = {}
        for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
            pos_data = data[data['player_position_id'] == position].copy()
            if not pos_data.empty:
                # Calculate ceiling score using value_score
                pos_data['value_score'] = (pos_data['projected_points'] / pos_data['salary']) * 1000
                pos_data['ceiling_score'] = pos_data['projected_points'] * (1 + pos_data['value_score'] / pos_data['value_score'].mean())
                
                analysis['tournament_plays'][position] = pos_data.nlargest(
                    3, 'ceiling_score'
                )[['player_name', 'salary', 'projected_points', 'ceiling_score']]
    except Exception as e:
        print(f"Error in tournament plays analysis: {str(e)}")
        analysis['tournament_plays'] = {}

    return analysis

def suggest_strategies_with_agent(data):
    """Generate strategy suggestions using the enhanced analysis."""
    analysis = analyze_data_for_strategy(data)
    
    message = []
    
    # 1. Value Plays
    message.append("🎯 TOP VALUE PLAYS BY POSITION:")
    for position, plays in analysis['value_plays'].items():
        if not plays.empty:
            message.append(f"\n{position} Standouts:")
            for _, play in plays.head(3).iterrows():
                message.append(
                    f"- {play['player_name']}: ${play['salary']:,} | "
                    f"{play['projected_points']:.1f} pts\n"
                    f"  Value vs Tier: {play['value_score']:.2f} pts/$K | "
                    f"Z-score: {play['points_zscore']:.2f}"
                )

    # 2. Stacking Opportunities
    message.append("\n\n🔄 OPTIMAL STACKING OPPORTUNITIES:")
    for stack in analysis['stacks'][:5]:
        message.append(
            f"- Stack: {stack['qb']} + {stack['receiver']}\n"
            f"  Combined Salary: ${stack['total_salary']:,} | "
            f"Projected: {stack['total_projection']:.1f} pts\n"
            f"  Stack Value: {stack['stack_value']:.3f} pts/$K"
        )

    # 3. Market Inefficiencies
    message.append("\n\n💰 MARKET INEFFICIENCIES:")
    for position, players in analysis['inefficiencies'].items():
        if not players.empty:
            message.append(f"\n{position} Inefficiencies:")
            for _, player in players.iterrows():
                message.append(
                    f"- {player['player_name']}: "
                    f"${player['salary']:,} | "
                    f"{player['projected_points']:.1f} pts\n"
                    f"  Outperforming salary by {player['points_vs_expected']:.1f} pts"
                )

    # 4. Tournament Plays
    message.append("\n\n🎲 TOURNAMENT OPPORTUNITIES:")
    for position, players in analysis['tournament_plays'].items():
        if not players.empty:
            message.append(f"\n{position} Tournament Plays:")
            for _, player in players.iterrows():
                message.append(
                    f"- {player['player_name']}: "
                    f"${player['salary']:,} | "
                    f"Ceiling Score: {player['ceiling_score']:.1f}"
                )

    # 5. Lineup Building Strategy
    message.append("\n\n🎮 LINEUP BUILDING STRATEGY:")
    message.append("1. Consider using one of the top stacks identified above")
    message.append("2. Fill remaining spots with value plays from different salary tiers")
    message.append("3. Target at least 2-3 tournament plays for GPPs")
    message.append("4. Look for market inefficiencies at FLEX position")

    return "\n".join(message)

class LineupOptimizerAgent:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        self.previous_lineups = []
        self.player_usage = {}
        self.strategy_boost = {}
        self.preferred_stacks = []

    def apply_strategy_adjustments(self, analysis: dict):
        """Apply strategy analysis to influence lineup generation"""
        self.strategy_boost = {}
        
        # Apply value play boosts
        for position, plays in analysis['value_plays'].items():
            if not plays.empty:
                # Calculate the mean value score for the position
                mean_value = plays['value_score'].mean()
                for _, play in plays.iterrows():
                    boost = play['value_score'] - mean_value  # Calculate boost relative to position mean
                    self.strategy_boost[play['player_name']] = boost
        
        # Apply tournament play boosts
        for position, plays in analysis['tournament_plays'].items():
            if not plays.empty and isinstance(plays, pd.DataFrame):  # Ensure we have a DataFrame
                for _, play in plays.iterrows():
                    current_boost = self.strategy_boost.get(play['player_name'], 0)
                    # Calculate ceiling boost without using mean
                    ceiling_boost = (play['ceiling_score'] / play['projected_points'] - 1) * 0.5
                    self.strategy_boost[play['player_name']] = max(current_boost, ceiling_boost)

        # Store preferred stacks
        self.preferred_stacks = [
            (stack['qb'], stack['receiver'])
            for stack in analysis['stacks'][:5]  # Top 5 stacks
        ] if analysis.get('stacks') else []

    def optimize_lineup(self, constraints: dict, diversity_constraint: set = None) -> dict:
        """Optimize a single lineup based on constraints."""
        # Generate multiple scenarios
        scenarios = self.generate_scenarios(num_scenarios=100)
        best_lineup = None
        best_score = -float('inf')

        for scenario_data in scenarios:
            try:
                prob = pulp.LpProblem("Fantasy Football", pulp.LpMaximize)
                
                # Convert data to records for optimization
                players = scenario_data.to_dict('records')
                
                # Create binary variables for each player
                player_vars = pulp.LpVariable.dicts("players", 
                                                ((p['player_name'], p['player_position_id']) for p in players), 
                                                cat='Binary')
                
                # Create FLEX variables
                flex_vars = pulp.LpVariable.dicts("flex",
                                            ((p['player_name'], p['player_position_id']) for p in players if p['player_position_id'] in ['RB', 'WR', 'TE']),
                                            cat='Binary')

                # Objective: Maximize projected points
                prob += pulp.lpSum([
                    float(p['projected_points']) * (
                        player_vars[p['player_name'], p['player_position_id']] +
                        (flex_vars.get((p['player_name'], p['player_position_id']), 0) 
                        if p['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                    )
                    for p in players
                ])

                # Position constraints
                prob += pulp.lpSum(player_vars[p['player_name'], 'QB'] for p in players if p['player_position_id'] == 'QB') == 1
                prob += pulp.lpSum(player_vars[p['player_name'], 'DST'] for p in players if p['player_position_id'] == 'DST') == 1
                prob += pulp.lpSum(player_vars[p['player_name'], 'RB'] for p in players if p['player_position_id'] == 'RB') == 2
                prob += pulp.lpSum(player_vars[p['player_name'], 'WR'] for p in players if p['player_position_id'] == 'WR') == 3
                prob += pulp.lpSum(player_vars[p['player_name'], 'TE'] for p in players if p['player_position_id'] == 'TE') == 1

                # FLEX position constraint
                prob += pulp.lpSum(flex_vars[p['player_name'], p['player_position_id']] 
                        for p in players if p['player_position_id'] in ['RB', 'WR', 'TE']) == 1

                # Prevent duplicate players
                for player in players:
                    if player['player_position_id'] in ['RB', 'WR', 'TE']:
                        prob += player_vars[player['player_name'], player['player_position_id']] + \
                                flex_vars[player['player_name'], player['player_position_id']] <= 1

                # Salary cap constraint
                prob += pulp.lpSum([
                    float(p['salary']) * (
                        player_vars[p['player_name'], p['player_position_id']] +
                        (flex_vars.get((p['player_name'], p['player_position_id']), 0) 
                        if p['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                    )
                    for p in players
                ]) <= 50000

                # Apply must_include constraints
                if 'must_include' in constraints:
                    for player_name in constraints['must_include']:
                        prob += pulp.lpSum([
                            player_vars[p['player_name'], p['player_position_id']] + 
                            (flex_vars.get((p['player_name'], p['player_position_id']), 0) 
                            if p['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                            for p in players if p['player_name'] == player_name
                        ]) == 1

                # Apply avoid_teams constraints
                if 'avoid_teams' in constraints:
                    for team in constraints['avoid_teams']:
                        prob += pulp.lpSum([
                            player_vars[p['player_name'], p['player_position_id']] +
                            (flex_vars.get((p['player_name'], p['player_position_id']), 0) 
                            if p['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                            for p in players if p['team'].lower() == team.lower()
                        ]) == 0

                # Solve the problem
                prob.solve(pulp.PULP_CBC_CMD(msg=False))

                if pulp.LpStatus[prob.status] == 'Optimal':
                    selected_players = []
                    for player in players:
                        base_val = player_vars[player['player_name'], player['player_position_id']].varValue
                        flex_val = flex_vars.get((player['player_name'], player['player_position_id']), 0)
                        if isinstance(flex_val, pulp.LpVariable):
                            flex_val = flex_val.varValue
                            
                        if base_val > 0.5 or flex_val > 0.5:
                            player_copy = player.copy()
                            player_copy['is_flex'] = (flex_val > 0.5)
                            selected_players.append(player_copy)

                    lineup = self.build_lineup(selected_players)
                    if 'error' not in lineup:
                        score = sum(float(player['projected_points']) for player in lineup.values())
                        if score > best_score:
                            best_score = score
                            best_lineup = lineup

            except Exception as e:
                print(f"Error in optimization: {str(e)}")
                continue

        return best_lineup if best_lineup else {'error': "No optimal solution found"}

    def generate_scenarios(self, num_scenarios=100):
        """Generate multiple scenarios with proper DataFrame operations."""
        scenarios = []
        for _ in range(num_scenarios):
            try:
                scenario = self.data.copy()
                
                # Add random noise to projected points
                noise = np.random.normal(1, 0.1, size=len(scenario))
                
                # Apply position-specific adjustments
                position_multipliers = scenario['player_position_id'].map({
                    'TE': 0.95,
                    'RB': 1.02,
                    'WR': 1.02,
                    'QB': 1.0,
                    'DST': 1.0
                }).fillna(1.0)
                
                # Apply strategy boosts
                strategy_boosts = pd.Series(
                    [self.strategy_boost.get(name, 0) for name in scenario['player_name']],
                    index=scenario.index
                )
                
                # Combine all adjustments
                total_multiplier = noise * position_multipliers * (1 + strategy_boosts)
                scenario['projected_points'] = scenario['projected_points'] * total_multiplier
                
                scenarios.append(scenario)
                
            except Exception as e:
                print(f"Error generating scenario: {str(e)}")
                continue
                
        return scenarios

    def build_lineup(self, selected_players):
        """Build a complete lineup from selected players"""
        # Sort by projected points for optimal FLEX placement
        selected_players.sort(key=lambda x: float(x['projected_points']), reverse=True)
        
        lineup = {}
        remaining_players = []

        # First pass: Fill QB and DST
        for player in selected_players[:]:
            if player['player_position_id'] == 'QB' and 'QB' not in lineup:
                lineup['QB'] = player
            elif player['player_position_id'] == 'DST' and 'DST' not in lineup:
                lineup['DST'] = player
            else:
                remaining_players.append(player)

        # Second pass: Fill RB/WR/TE positions with best available
        rb_count = 0
        wr_count = 0
        te_filled = False

        for player in remaining_players[:]:
            if player['player_position_id'] == 'RB' and rb_count < 2 and not player.get('is_flex', False):
                lineup[f'RB{rb_count + 1}'] = player
                rb_count += 1
                remaining_players.remove(player)
            elif player['player_position_id'] == 'WR' and wr_count < 3 and not player.get('is_flex', False):
                lineup[f'WR{wr_count + 1}'] = player
                wr_count += 1
                remaining_players.remove(player)
            elif player['player_position_id'] == 'TE' and not te_filled and not player.get('is_flex', False):
                lineup['TE'] = player
                te_filled = True
                remaining_players.remove(player)

        # Last pass: Find FLEX player
        if remaining_players:
            flex_player = max(remaining_players, key=lambda x: float(x['projected_points']))
            lineup['FLEX'] = flex_player

        return lineup

    def generate_lineups(self, constraints: dict) -> list:
        """Generate multiple lineups with strategy consideration"""
        num_lineups = int(constraints.get('num_lineups', 1))
        max_exposure = float(constraints.get('max_exposure', 0.3))
        lineups = []
        
        # Add diversity constraints for each iteration
        used_players = set()
        
        for i in range(num_lineups):
            # Generate lineup with diversity constraint
            lineup = self.optimize_lineup(constraints, diversity_constraint=used_players)
            
            if 'error' not in lineup:
                lineups.append(lineup)
                
                # Update player usage and used_players set
                for player in lineup.values():
                    if player:
                        player_name = player['player_name']
                        self.player_usage[player_name] = self.player_usage.get(player_name, 0) + 1
                        used_players.add(player_name)
                
                # Apply exposure limits for next iteration
                if i < num_lineups - 1:
                    for player_name, count in self.player_usage.items():
                        if count / (i + 1) > max_exposure:
                            if 'avoid_players' not in constraints:
                                constraints['avoid_players'] = []
                            if player_name not in constraints.get('must_include', []):
                                constraints['avoid_players'].append(player_name)

        return lineups
    
    def get_average_projected_points(self, player_name):
        """Calculate average projected points for a player across all lineups"""
        total_points = 0
        appearances = 0
        for lineup in self.previous_lineups:
            for player in lineup.values():
                if player and player['player_name'] == player_name:
                    total_points += float(player['projected_points'])
                    appearances += 1
        return total_points / appearances if appearances > 0 else 0

# Initialize optimizer agent
optimizer_agent = LineupOptimizerAgent(
    name="LineupOptimizer",
    data=data
)

def process_user_input_and_strategies(user_proxy, user_input_agent, user_input):
    """Process user input into constraints"""
    if not user_input.strip():
        return {}
    
    user_input_agent.reset()
    user_proxy.send(user_input, user_input_agent, request_reply=True)
    response = user_input_agent.last_message()['content']
    try:
        constraints = json.loads(response)
    except json.JSONDecodeError:
        constraints = {}
    return constraints

def display_lineup(lineup, constraints, strategy_insights=""):
    """Display lineup with applied strategy insights"""
    position_order = ['QB', 'RB1', 'RB2', 'WR1', 'WR2', 'WR3', 'TE', 'FLEX', 'DST']
    
    lineup_data = []
    total_salary = 0
    total_projected_points = 0
    
    for position in position_order:
        player = lineup.get(position)
        if player:
            salary = float(player['salary'])
            projected_points = float(player['projected_points'])
            lineup_data.append({
                'Position': position,
                'Player': player['player_name'],
                'Team': player['team'].upper(),
                'Projected Points': f"{projected_points:.1f}",
                'Salary': f"${salary:,.0f}"
            })
            total_salary += salary
            total_projected_points += projected_points
        else:
            lineup_data.append({
                'Position': position,
                'Player': '',
                'Team': '',
                'Projected Points': '',
                'Salary': ''
            })
    
    df = pd.DataFrame(lineup_data)
    st.table(df)
    st.write(f"**Total Salary:** ${total_salary:,.0f}")
    st.write(f"**Total Projected Points:** {total_projected_points:.2f}")

    # Add strategy insights if available
    if strategy_insights:
        applied_strategies = explain_lineup_with_architect(lineup, constraints, strategy_insights)
        if applied_strategies:
            st.markdown("**Applied Strategies:**")
            st.markdown(applied_strategies)

def display_player_exposure(optimizer_agent):
    """Display player exposure statistics"""
    st.subheader('Player Exposure')
    total_lineups = len(optimizer_agent.previous_lineups)
    if total_lineups == 0:
        st.write("No lineups generated yet.")
        return

    exposure_data = []
    for player_name, count in optimizer_agent.player_usage.items():
        avg_projected_points = optimizer_agent.get_average_projected_points(player_name)
        exposure_data.append({
            'Player': player_name,
            'Lineups Used': count,
            'Exposure (%)': f"{(count / total_lineups * 100):.1f}%",
            'Avg Projected Points': f"{avg_projected_points:.1f}"
        })
    
    exposure_df = pd.DataFrame(exposure_data)
    exposure_df = exposure_df.sort_values(by='Lineups Used', ascending=False)
    st.table(exposure_df)

def create_fantasy_football_ui():
    st.title('Daily Fantasy Football Lineup Generator')
    
    # Strategy Analysis Section
    with st.expander("View Strategy Analysis", expanded=True):
        st.subheader("Current Slate Analysis")
        if st.button("Generate Strategy Analysis"):
            with st.spinner("Analyzing slate..."):
                strategy_insights = suggest_strategies_with_agent(data)
                st.session_state.strategy_insights = strategy_insights
                st.markdown(strategy_insights)
    
    # Value Plays Section
    with st.expander("View Value Analysis", expanded=False):
        if st.button("Show Value Analysis"):
            analysis = analyze_data_for_strategy(data)
            
            # Display Value Plays
            st.subheader("Value Plays by Position")
            for position, plays in analysis['value_plays'].items():
                if not plays.empty:
                    st.write(f"**{position}**")
                    st.dataframe(plays.style.format({
                        'salary': '${:,.0f}',
                        'projected_points': '{:.2f}',
                        'value_vs_tier': '{:.2f}',
                        'points_zscore': '{:.2f}'
                    }))
            
            # Display Stack Analysis
            st.subheader("Top Stacking Opportunities")
            stacks_df = pd.DataFrame(analysis['stacks'][:10])
            st.dataframe(stacks_df.style.format({
                'total_salary': '${:,.0f}',
                'total_projection': '{:.2f}',
                'stack_value': '{:.3f}'
            }))
    
    # User Input Section
    user_input = st.text_area('Enter your lineup requests:', '', height=75)
    
    col1, col2 = st.columns(2)
    with col1:
        num_lineups = st.number_input('Number of Lineups', min_value=1, max_value=150, value=1)
    with col2:
        max_exposure = st.slider('Maximum Player Exposure (%)', min_value=0, max_value=100, value=30)

    if st.button('Generate Lineup(s)'):
        # Get fresh strategy insights if none exist
        if not hasattr(st.session_state, 'strategy_insights'):
            with st.spinner("Analyzing strategies..."):
                strategy_insights = suggest_strategies_with_agent(data)
                st.session_state.strategy_insights = strategy_insights
        
        # Process constraints
        constraints = process_user_input_and_strategies(user_proxy, user_input_agent, user_input)
        constraints['num_lineups'] = num_lineups
        constraints['max_exposure'] = max_exposure / 100
        
        # Generate lineups
        with st.spinner("Generating optimized lineups..."):
            lineups = optimizer_agent.generate_lineups(constraints)

        if not lineups:
            st.error("No lineups were generated.")
        else:
            for idx, lineup in enumerate(lineups):
                st.subheader(f'Lineup {idx + 1}')
                display_lineup(lineup, constraints, st.session_state.strategy_insights)

            display_player_exposure(optimizer_agent)

    if st.button('Reset'):
        optimizer_agent.previous_lineups = []
        optimizer_agent.player_usage = {}
        st.session_state.clear()
        st.experimental_rerun()

def explain_lineup_with_architect(lineup: dict, constraints: dict, strategy_insights: str) -> str:
    """Create concise bullet points of applied strategies"""
    applied_strategies = []
    
    # Track players by team for stack identification
    team_players = {}
    for pos, player in lineup.items():
        if player:
            team = player['team']
            team_players.setdefault(team, []).append(player)
    
    # 1. Analyze Stacks
    for team, players in team_players.items():
        if len(players) >= 2:
            qb_player = next((p for p in players if p['player_position_id'] == 'QB'), None)
            receivers = [p for p in players if p['player_position_id'] in ['WR', 'TE']]
            
            if qb_player and receivers:
                stack_value = qb_player['projected_points'] + sum(r['projected_points'] for r in receivers)
                stack_salary = qb_player['salary'] + sum(r['salary'] for r in receivers)
                
                applied_strategies.append(
                    f"• {team.upper()} Stack:\n"
                    f"  QB: {qb_player['player_name']} + {', '.join(r['player_name'] for r in receivers)}\n"
                    f"  Combined Proj: {stack_value:.1f} pts | Cost: ${stack_salary:,}"
                )
    
    # 2. Identify Value Plays
    for pos, player in lineup.items():
        if player:
            value_score = float(player['projected_points']) / float(player['salary']) * 1000
            if value_score > 2.0:  # More than 2 points per $1000
                applied_strategies.append(
                    f"• Value Play: {player['player_name']} ({pos})\n"
                    f"  {player['projected_points']:.1f} pts / ${player['salary']:,}\n"
                    f"  ({value_score:.2f} pts/$1K)"
                )
    
    # 3. Check for Correlation with Game Stacks
    team_counts = {}
    for pos, player in lineup.items():
        if player:
            team_counts[player['team']] = team_counts.get(player['team'], 0) + 1
    
    for team, count in team_counts.items():
        if count >= 3:
            players = [p for pos, p in lineup.items() if p and p['team'] == team]
            total_proj = sum(float(p['projected_points']) for p in players)
            applied_strategies.append(
                f"• Heavy {team.upper()} Exposure:\n"
                f"  {', '.join(p['player_name'] for p in players)}\n"
                f"  Combined Projection: {total_proj:.1f} pts"
            )

    return "\n".join(applied_strategies) if applied_strategies else ""

# Initialize AutoGen agents
config_list = [
    {
        "model": "gpt-4",
        "api_key": os.environ.get("OPENAI_API_KEY"),
    }
]

user_proxy = UserProxyAgent(
    name="UserProxy",
    system_message="A human user who will provide input about fantasy football lineup constraints.",
    code_execution_config=False,
)

user_input_agent = AssistantAgent(
    name="Interpreter",
    system_message="""You are a helpful assistant that interprets user input about fantasy football lineup constraints.
    Convert natural language into a JSON format with the following possible keys:
    - must_include: list of player names to include
    - avoid_teams: list of team abbreviations to avoid
    - stack_teams: list of team abbreviations to stack
    - num_lineups: integer number of lineups to generate
    - max_exposure: float between 0 and 1 for maximum player exposure
    """,
    llm_config={"config_list": config_list},
)

# Run the app
if __name__ == "__main__":
    create_fantasy_football_ui()