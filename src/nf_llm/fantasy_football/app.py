import os
import pulp
import pandas as pd
import streamlit as st
from autogen import AssistantAgent, UserProxyAgent
import pathlib

_secret_path = pathlib.Path("/run/secrets/openai_api_key")
if not os.getenv("OPENAI_API_KEY") and _secret_path.exists():
    os.environ["OPENAI_API_KEY"] = _secret_path.read_text().strip()

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

# Add this new function after the preprocess_data function
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

# LineupOptimizerAgent class
class LineupOptimizerAgent:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        self.previous_lineups = []
        self.player_usage = {}  # Track player usage

    def optimize_lineup(self, constraints: dict, strategies: dict = {}, diversity_constraint: set = None) -> dict:
        players = self.data.to_dict('records')
        prob = pulp.LpProblem("Fantasy Football", pulp.LpMaximize)

        player_vars = pulp.LpVariable.dicts("players", 
                                            ((p['player_name'], p['player_position_id']) for p in players), 
                                            cat='Binary')

        # Objective: Maximize projected points with strategy bonuses
        prob += pulp.lpSum([
            (player['projected_points'] + self.apply_strategy_bonus(player, strategies)) * 
            player_vars[player['player_name'], player['player_position_id']]
            for player in players
        ])

        # Salary cap constraint
        prob += pulp.lpSum([
            player['salary'] * player_vars[player['player_name'], player['player_position_id']] 
            for player in players
        ]) <= 50000

        # Position constraints
        # Exactly 1 QB
        prob += pulp.lpSum([
            player_vars[p['player_name'], 'QB']
            for p in players if p['player_position_id'] == 'QB'
        ]) == 1

        # At least 2 RBs
        prob += pulp.lpSum([
            player_vars[p['player_name'], 'RB']
            for p in players if p['player_position_id'] == 'RB'
        ]) >= 2

        # At least 3 WRs
        prob += pulp.lpSum([
            player_vars[p['player_name'], 'WR']
            for p in players if p['player_position_id'] == 'WR'
        ]) >= 3

        # At least 1 TE
        prob += pulp.lpSum([
            player_vars[p['player_name'], 'TE']
            for p in players if p['player_position_id'] == 'TE'
        ]) >= 1

        # Exactly 1 DST
        prob += pulp.lpSum([
            player_vars[p['player_name'], 'DST']
            for p in players if p['player_position_id'] == 'DST'
        ]) == 1

        # Total players constraint
        prob += pulp.lpSum([
            player_vars[p['player_name'], p['player_position_id']] 
            for p in players
        ]) == 9

        # FLEX position constraints
        # Ensure that the sum of RBs, WRs, and TEs accounts for the FLEX position
        prob += pulp.lpSum([
            player_vars[p['player_name'], p['player_position_id']]
            for p in players if p['player_position_id'] in ['RB', 'WR', 'TE']
        ]) >= 7  # Minimum RBs, WRs, TEs including FLEX (2 RB + 3 WR + 1 TE + 1 FLEX)

        # Apply must_include constraints
        if 'must_include' in constraints:
            for player_name in constraints['must_include']:
                prob += pulp.lpSum([
                    player_vars[p['player_name'], p['player_position_id']] 
                    for p in players if p['player_name'] == player_name
                ]) == 1

        # Apply avoid_teams constraints
        if 'avoid_teams' in constraints:
            for team in constraints['avoid_teams']:
                prob += pulp.lpSum([
                    player_vars[p['player_name'], p['player_position_id']]
                    for p in players if p['team'] == team.lower()
                ]) == 0

        # Apply diversity constraints
        if diversity_constraint:
            for player_name in diversity_constraint:
                prob += pulp.lpSum([
                    player_vars[player_name, p['player_position_id']]
                    for p in players if p['player_name'] == player_name
                ]) == 0

        # Solve the problem
        prob.solve()

        if pulp.LpStatus[prob.status] != 'Optimal':
            return {'error': f"Optimization failed: {pulp.LpStatus[prob.status]}"}

        return self.build_lineup(player_vars, players)


    def apply_strategy_bonus(self, player, strategies):
        bonus = 0
        if 'stack_teams' in strategies and player['team'] in [team.lower() for team in strategies['stack_teams']]:
            bonus += 1.5
        if 'value_players' in strategies and player['player_name'] in strategies['value_players']:
            bonus += 1.0
        if 'avoid_players' in strategies and player['player_name'] in strategies['avoid_players']:
            bonus -= 2.0
        return bonus

    def build_lineup(self, player_vars, players):
        lineup = {}

        for player in players:
            if player_vars[player['player_name'], player['player_position_id']].varValue == 1:
                position = player['player_position_id']
                key = position
                if position == 'RB':
                    key = 'RB1' if 'RB1' not in lineup else 'RB2' if 'RB2' not in lineup else 'FLEX'
                elif position == 'WR':
                    key = 'WR1' if 'WR1' not in lineup else 'WR2' if 'WR2' not in lineup else 'WR3' if 'WR3' not in lineup else 'FLEX'
                elif position == 'TE':
                    key = 'TE' if 'TE' not in lineup else 'FLEX'
                elif position == 'DST':
                    key = 'DST'
                elif position == 'QB':
                    key = 'QB'
                if key not in lineup:
                    lineup[key] = player

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


# Initialize the optimizer agent
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
    max_exposure = st.slider('Maximum Player Exposure (%)', min_value=0, max_value=100, value=65)

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

# Initialize the database
from nf_llm.db import init_db
init_db()

# Run the app
if __name__ == "__main__":
    create_fantasy_football_ui()