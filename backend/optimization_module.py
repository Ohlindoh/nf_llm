import pandas as pd
import pulp

# Read player data
def read_player_data():
    file_path = 'backend/data/week13_sunday_all.csv'  # Hardcoded path
    return pd.read_csv(file_path)

# Create the optimization problem
def create_optimizer(players_df):
    prob = pulp.LpProblem("LineupOptimizer", pulp.LpMaximize)
    player_vars = {row['player_name']: pulp.LpVariable(row['player_name'], cat='Binary') 
                   for index, row in players_df.iterrows()}

    # Objective function: Maximize projected points
    prob += pulp.lpSum([player_vars[row['player_name']] * row['projected_points'] 
                        for index, row in players_df.iterrows()])

    # Salary cap constraint
    prob += pulp.lpSum([player_vars[row['player_name']] * row['salary'] 
                        for index, row in players_df.iterrows()]) <= 50000

    # Position constraints
    prob += pulp.lpSum([player_vars[player] for player in player_vars 
                        if players_df.loc[player, 'player_position_id'] == 'QB']) == 1
    prob += pulp.lpSum([player_vars[player] for player in player_vars 
                        if players_df.loc[player, 'player_position_id'] == 'RB']) == 2
    prob += pulp.lpSum([player_vars[player] for player in player_vars 
                        if players_df.loc[player, 'player_position_id'] == 'WR']) == 3
    prob += pulp.lpSum([player_vars[player] for player in player_vars 
                        if players_df.loc[player, 'player_position_id'] == 'TE']) == 1
    prob += pulp.lpSum([player_vars[player] for player in player_vars 
                        if players_df.loc[player, 'player_position_id'] == 'DST']) == 1

    # Flex player constraint (RB, WR, or TE, and not already included)
    flex_players = [player for player in player_vars if players_df.loc[player, 'player_position_id'] in ['RB', 'WR', 'TE']]
    prob += pulp.lpSum([player_vars[player] for player in flex_players]) == 4  # Total of 4 including the RB, WR, TE already counted

    return prob, player_vars

def stack_team(prob, player_vars, players_data, team_id, positions):
    for position in positions:
        # Select players from the specified team and position
        team_players = [player for player, data in players_data.items() 
                        if data['player_team_id'] == team_id and data['player_position_id'] == position]
        
        # Add a constraint to ensure at least one player from this group is in the lineup
        prob += pulp.lpSum([player_vars[player] for player in team_players]) >= 1

# Function to add constraints
def add_constraints(prob, player_vars, players_df, constraints):
    if constraints == None:
        pass
    else:
        for constraint in constraints:
            if constraint['type'] == 'stack_team':
                stack_team(prob, player_vars, players_df, constraint['team_id'], constraint['positions'])
            # Add other constraint types here

# Main function to run the optimization
def run_optimization(constraints):
    players_df = read_player_data()
    prob, player_vars = create_optimizer(players_df)
    add_constraints(prob, player_vars, players_df, constraints)
    prob.solve()

    return [player for player in player_vars if pulp.value(player_vars[player]) == 1]
