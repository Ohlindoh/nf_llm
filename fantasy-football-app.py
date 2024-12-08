import os
import pulp
import pandas as pd
import numpy as np
import json
import streamlit as st
import autogen
from autogen import AssistantAgent, UserProxyAgent

# Initialize LLM configuration
llm_config = {
    "model": "gpt-4",
    "api_key": os.environ.get("OPENAI_API_KEY"),
    "temperature": 0,
}

# Load data
data_file = 'data/merged_fantasy_football_data.csv'
data = pd.read_csv(data_file)

# Preprocess data
def preprocess_data(data):
    data['player_name'] = data['player_name'].str.replace(' ', '').str.lower()

    # Rename 'player_team_id' to 'team' if necessary
    if 'player_team_id' in data.columns:
        data.rename(columns={'player_team_id': 'team'}, inplace=True)
    
    data['team'] = data['team'].str.lower()
    data['salary'] = data['salary'].replace('[\$,]', '', regex=True).astype(float)
    data['projected_points'] = pd.to_numeric(data['projected_points'], errors='coerce')
    data['value'] = data['projected_points'] / data['salary']
    return data

data = preprocess_data(data)

def get_undervalued_players(data, top_n=5):
    undervalued = {}
    for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
        position_data = data[data['player_position_id'] == position].sort_values('value', ascending=False)
        undervalued[position] = position_data.head(top_n)[['player_name', 'team', 'salary', 'projected_points', 'value']]
    return undervalued

# Initialize agents
user_proxy = UserProxyAgent(
    name="UserProxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=0
)

user_input_agent = AssistantAgent(
    name="UserInputAgent",
    llm_config=llm_config,
    system_message="""
You are an assistant that processes user requests for fantasy football lineups.
Parse the user's natural language input and convert it into a structured JSON format for lineup optimization.
If the input doesn't contain specific constraints, return an empty JSON object.
Use the following examples as a guide:

Input: "I want Justin Jefferson and Dalvin Cook in my lineup"
Output: {"must_include": ["justinjefferson", "dalvincook"]}

Input: "Avoid players from the Jets"
Output: {"avoid_teams": ["nyj"]}

Input: "Focus on stacking players from Kansas City Chiefs"
Output: {"stack_teams": ["kc"]}

Input: "Limit exposure of Patrick Mahomes to 50%"
Output: {"player_exposure_limits": {"patrickmahomes": 0.5}}

Input: "Generate 5 unique lineups"
Output: {"num_lineups": 5}

Provide your output as a valid JSON object.
"""
)

class LineupOptimizerAgent:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        self.previous_lineups = []
        self.player_usage = {}

    def generate_scenarios(self, num_scenarios=100):
        scenarios = []
        for _ in range(num_scenarios):
            scenario = self.data.copy()
            
            # Add position-specific noise
            for idx, row in scenario.iterrows():
                position = row['player_position_id']
                base_noise = np.random.normal(1, 0.1)  # Base 10% standard deviation
                
                # Adjust noise based on position for FLEX consideration
                if position == 'TE':
                    # Add slight downward bias to TEs for FLEX consideration
                    position_multiplier = 0.95  # 5% downward bias
                elif position in ['RB', 'WR']:
                    # Slight upward bias for traditional FLEX positions
                    position_multiplier = 1.02  # 2% upward bias
                else:
                    position_multiplier = 1.0
                    
                scenario.at[idx, 'projected_points'] *= (base_noise * position_multiplier)
            
            scenarios.append(scenario)
        return scenarios

    def optimize_lineup(self, constraints: dict, strategies: dict = {}, diversity_constraint: set = None) -> dict:
        scenarios = self.generate_scenarios(num_scenarios=100)
        best_lineup = None
        best_score = -float('inf')

        for scenario in scenarios:
            prob = pulp.LpProblem("Fantasy Football", pulp.LpMaximize)
            
            players = scenario.to_dict('records')
            # Create binary variables for player selection
            player_vars = pulp.LpVariable.dicts("players", 
                                              ((p['player_name'], p['player_position_id']) for p in players), 
                                              cat='Binary')
            
            # Create additional binary variables for FLEX position
            flex_vars = pulp.LpVariable.dicts("flex",
                                           ((p['player_name'], p['player_position_id']) for p in players if p['player_position_id'] in ['RB', 'WR', 'TE']),
                                           cat='Binary')

            # Objective: Maximize total projected points
            prob += pulp.lpSum([
                float(player['projected_points']) * (
                    player_vars[player['player_name'], player['player_position_id']] +
                    (flex_vars.get((player['player_name'], player['player_position_id']), 0) 
                     if player['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                )
                for player in players
            ])

            # Basic position requirements
            prob += pulp.lpSum([player_vars[p['player_name'], 'QB'] for p in players if p['player_position_id'] == 'QB']) == 1
            prob += pulp.lpSum([player_vars[p['player_name'], 'DST'] for p in players if p['player_position_id'] == 'DST']) == 1
            
            # Base position requirements (not counting FLEX)
            rb_vars = [player_vars[p['player_name'], 'RB'] for p in players if p['player_position_id'] == 'RB']
            wr_vars = [player_vars[p['player_name'], 'WR'] for p in players if p['player_position_id'] == 'WR']
            te_vars = [player_vars[p['player_name'], 'TE'] for p in players if p['player_position_id'] == 'TE']
            
            prob += pulp.lpSum(rb_vars) == 2  # Exactly 2 RB in base positions
            prob += pulp.lpSum(wr_vars) == 3  # Exactly 3 WR in base positions
            prob += pulp.lpSum(te_vars) == 1  # Exactly 1 TE in base position
            
            # FLEX position constraints
            # Only one player can be in FLEX
            prob += pulp.lpSum([flex_vars[p['player_name'], p['player_position_id']] 
                              for p in players if p['player_position_id'] in ['RB', 'WR', 'TE']]) == 1
            
            # A player can't be in both base position and FLEX
            for player in players:
                if player['player_position_id'] in ['RB', 'WR', 'TE']:
                    prob += player_vars[player['player_name'], player['player_position_id']] + \
                            flex_vars[player['player_name'], player['player_position_id']] <= 1

            # Salary cap includes both base and FLEX positions
            prob += pulp.lpSum([
                float(player['salary']) * (
                    player_vars[player['player_name'], player['player_position_id']] +
                    (flex_vars.get((player['player_name'], player['player_position_id']), 0) 
                     if player['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                )
                for player in players
            ]) <= 50000

            # Apply constraints...
            if 'must_include' in constraints:
                for player_name in constraints['must_include']:
                    prob += pulp.lpSum([
                        player_vars[p['player_name'], p['player_position_id']] + 
                        (flex_vars.get((p['player_name'], p['player_position_id']), 0) 
                         if p['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                        for p in players if p['player_name'] == player_name
                    ]) == 1

            if 'avoid_teams' in constraints:
                for team in constraints['avoid_teams']:
                    prob += pulp.lpSum([
                        player_vars[p['player_name'], p['player_position_id']] +
                        (flex_vars.get((p['player_name'], p['player_position_id']), 0) 
                         if p['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                        for p in players if p['team'] == team.lower()
                    ]) == 0

            if diversity_constraint:
                for player_name in diversity_constraint:
                    prob += pulp.lpSum([
                        player_vars[p['player_name'], p['player_position_id']] +
                        (flex_vars.get((p['player_name'], p['player_position_id']), 0) 
                         if p['player_position_id'] in ['RB', 'WR', 'TE'] else 0)
                        for p in players if p['player_name'] == player_name
                    ]) == 0

            # Solve this scenario
            prob.solve()

            if pulp.LpStatus[prob.status] == 'Optimal':
                # Build lineup considering both base and FLEX positions
                selected_players = []
                for player in players:
                    base_val = player_vars[player['player_name'], player['player_position_id']].varValue
                    flex_val = flex_vars.get((player['player_name'], player['player_position_id']), 0)
                    if isinstance(flex_val, pulp.LpVariable):
                        flex_val = flex_val.varValue
                        
                    if base_val > 0.5 or flex_val > 0.5:  # Account for floating point imprecision
                        player_copy = player.copy()
                        player_copy['is_flex'] = (flex_val > 0.5)
                        selected_players.append(player_copy)

                lineup = self.build_lineup(selected_players)
                
                if 'error' not in lineup:
                    score = sum(float(player['projected_points']) for player in lineup.values())
                    if score > best_score:
                        best_score = score
                        best_lineup = lineup

        return best_lineup if best_lineup else {'error': "Optimization failed for all scenarios"}

    def build_lineup(self, selected_players):
        # Sort by projected points
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
            if player['player_position_id'] == 'RB' and rb_count < 2:
                lineup[f'RB{rb_count + 1}'] = player
                rb_count += 1
                remaining_players.remove(player)
            elif player['player_position_id'] == 'WR' and wr_count < 3:
                lineup[f'WR{wr_count + 1}'] = player
                wr_count += 1
                remaining_players.remove(player)
            elif player['player_position_id'] == 'TE' and not te_filled:
                lineup['TE'] = player
                te_filled = True
                remaining_players.remove(player)

        # Last pass: Best remaining player goes to FLEX
        if remaining_players:
            lineup['FLEX'] = max(remaining_players, key=lambda x: float(x['projected_points']))

        return lineup

    def generate_lineups(self, constraints: dict) -> list:
        num_lineups = int(constraints.get('num_lineups', 1))
        max_exposure = constraints.get('max_exposure', 1.0)
        lineups = []

        for i in range(num_lineups):
            exposure_constraint = set()
            # Update exposure constraints based on current player usage
            for player_name, count in self.player_usage.items():
                exposure = count / (i + 1)
                if exposure >= max_exposure:
                    exposure_constraint.add(player_name)

            # Generate lineup with current exposure constraints
            lineup = self.optimize_lineup(
                constraints,
                strategies=constraints,  # Use constraints as strategies if applicable
                diversity_constraint=exposure_constraint
            )

            if 'error' in lineup:
                st.warning(f"Lineup {i + 1} could not be generated: {lineup['error']}")
                continue

            lineups.append(lineup)
            self.previous_lineups.append(lineup)

            # Update player usage
            for player in lineup.values():
                if player:
                    player_name = player['player_name']
                    self.player_usage[player_name] = self.player_usage.get(player_name, 0) + 1

        return lineups
    
    def get_average_projected_points(self, player_name):
        total_points = 0
        appearances = 0
        for lineup in self.previous_lineups:
            for player in lineup.values():
                if player and player['player_name'] == player_name:
                    total_points += player['projected_points']
                    appearances += 1
        return total_points / appearances if appearances > 0 else 0

# Initialize both optimizer agents
optimizer_agent = LineupOptimizerAgent(
    name="LineupOptimizer",
    data=data
)

# Function to process user input and strategies
def process_user_input_and_strategies(user_proxy, user_input_agent, user_input):
    if not user_input.strip():
        return {}
    else:
        user_input_agent.reset()
        user_proxy.send(user_input, user_input_agent, request_reply=True)
        response = user_input_agent.last_message()['content']
        try:
            constraints = json.loads(response)
        except json.JSONDecodeError:
            constraints = {}
        return constraints

# Function to display lineup
def display_lineup(lineup):
    # Define the desired order of positions
    position_order = ['QB', 'RB1', 'RB2', 'WR1', 'WR2', 'WR3', 'TE', 'FLEX', 'DST']
    
    # Build the DataFrame with positions in the specified order
    lineup_data = []
    total_salary = 0
    total_projected_points = 0
    for position in position_order:
        player = lineup.get(position)
        if player:
            salary = player['salary']
            projected_points = player['projected_points']
            lineup_data.append({
                'Position': position,
                'Player': player['player_name'],
                'Team': player['team'].upper(),
                'Projected Points': projected_points,
                'Salary': f"${salary}"
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
    
    # Display the lineup table
    st.table(df)
    
    # Display total salary and projected points
    st.write(f"**Total Salary:** ${total_salary}")
    st.write(f"**Total Projected Points:** {total_projected_points:.2f}")

def display_player_exposure(optimizer_agent):
    st.subheader('Player Exposure')
    total_lineups = len(optimizer_agent.previous_lineups)
    exposure_data = []
    for player_name, count in optimizer_agent.player_usage.items():
        avg_projected_points = optimizer_agent.get_average_projected_points(player_name)
        exposure_data.append({
            'Player': player_name,
            'Lineups Used': count,
            'Exposure (%)': round((count / total_lineups) * 100, 2),
            'Avg Projected Points': round(avg_projected_points, 2)
        })
    exposure_df = pd.DataFrame(exposure_data)
    exposure_df = exposure_df.sort_values(by='Exposure (%)', ascending=False)
    st.table(exposure_df)

# Create UI using Streamlit
def create_fantasy_football_ui():
    st.title('Daily Fantasy Football Lineup Generator')

    # Add a collapsible section for undervalued players
    with st.expander("View Most Undervalued Players", expanded=False):
        st.subheader('Most Undervalued Players')
        undervalued_players = get_undervalued_players(data)
        for position, players in undervalued_players.items():
            st.write(f"**{position}**")
            st.dataframe(players.style.format({
                'salary': '${:,.0f}',
                'projected_points': '{:.2f}',
                'value': '{:.4f}'
            }))
            st.write("---")  # Add a separator between positions

    user_input = st.text_area('Enter your lineup requests:', '', height=75)
    num_lineups = st.number_input('Number of Lineups', min_value=1, max_value=150, value=1)
    max_exposure = st.slider('Maximum Player Exposure (%)', min_value=0, max_value=100, value=30)

    generate_button = st.button('Generate Lineup(s)')

    if generate_button:
        # Process user input and strategies
        constraints = process_user_input_and_strategies(user_proxy, user_input_agent, user_input)
        constraints['num_lineups'] = num_lineups
        constraints['max_exposure'] = max_exposure / 100  # Convert to decimal

        lineups = optimizer_agent.generate_lineups(constraints)

        if not lineups:
            st.error("No lineups were generated.")
        else:
            for idx, lineup in enumerate(lineups):
                st.subheader(f'Lineup {idx + 1}')
                display_lineup(lineup)
            display_player_exposure(optimizer_agent)
            
    if st.button('Reset'):
        optimizer_agent.previous_lineups = []
        optimizer_agent.player_usage = {}
        st.experimental_rerun()                                                     
# Run the app
if __name__ == "__main__":
    create_fantasy_football_ui()