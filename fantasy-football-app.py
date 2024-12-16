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
    "model": "gpt-4o-mini",
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

strategy_agent = AssistantAgent(
    name="StrategyAgent",
    llm_config=llm_config,
    system_message="""You are an expert DFS Strategy Analyst specializing in NFL lineup optimization.
        Your analysis combines value-based metrics, game theory, and correlation analysis to find hidden opportunities.

        Key Analysis Areas:
        1. Value-Based Analysis:
            - Calculate points per dollar (Projected Points / Salary * 1000)
            - Identify players with positive rank vs. salary disparities
            - Flag value plays where ECR ranking suggests higher potential than salary indicates
            - Find players outperforming their salary tier expectations
            - Spot positional advantages where pricing inefficiencies exist

        2. Game Theory Advantages:
            - Identify high-upside players likely to be under-owned
            - Find optimal contrarian stacks that maximize differentiation
            - Spot salary-saving combinations that enable unique roster constructions
            - Calculate ownership leverage points
            - Identify tournament vs. cash game plays

        3. Stack Analysis:
            - Calculate optimal QB-WR/TE combinations considering salary and projected ownership
            - Identify bring-back opportunities from opposing teams
            - Find correlated defensive matchups
            - Calculate stack leverage scores
            - Evaluate game environment factors

        4. Market Inefficiency Analysis:
            - Compare salary vs. projected points across positions
            - Identify pricing gaps that enable unique roster constructions
            - Calculate position-specific value thresholds
            - Find salary tier arbitrage opportunities
            - Spot week-specific pricing inefficiencies

        5. Advanced Metrics:
            - Calculate z-scores within salary tiers
            - Evaluate correlation-adjusted projections
            - Analyze historical performance patterns
            - Consider game script implications
            - Factor in opposing defense strength

        For each analysis component:
        - Provide specific actionable player recommendations
        - Include exact salary implications
        - Consider correlation effects
        - Factor in ownership projections
        - Assess risk-reward scenarios
        
        When analyzing data, specifically look for:
        1. Salary Tier Analysis:
            - Players outperforming their salary tier by >1 standard deviation
            - Value discrepancies between positions
            - Opportunities for salary arbitrage

        2. Correlation Opportunities:
            - QB-WR/TE stacks under 35% of total salary cap
            - Game stacks with positive game script correlation
            - Defense/QB correlation opportunities

        3. Tournament Plays:
            - High ceiling, low floor players
            - Unique roster construction paths
            - Leverage against popular plays

        4. Hidden Value:
            - Secondary receivers in good matchups
            - Backup RBs with increased opportunity
            - Defensive matchups against weak offenses

        Always provide specific, actionable insights including:
        - Exact player names and reasoning
        - Salary implications of recommendations
        - Expected ownership impact
        - Correlation benefits
        - Risk assessment
        - Specific lineup construction strategies

        Format your analysis with clear sections using emojis:
        🎯 TOP VALUE PLAYS
        🎲 CONTRARIAN OPPORTUNITIES
        🔄 STACKING ANALYSIS
        💰 MARKET INEFFICIENCIES
        🎮 LINEUP STRATEGIES

        Base all recommendations on data while incorporating NFL game theory and strategic concepts."""
    )
def analyze_data_for_strategy(data: pd.DataFrame) -> dict:
    """Analyze fantasy football data for strategic insights."""
    analysis = {}
    
    # Calculate base metrics
    data['value_score'] = data['projected_points'] / data['salary']
    data['salary_tier'] = pd.qcut(data['salary'], q=4, labels=['Budget', 'Value', 'Premium', 'Elite'])
    
    # 1. Value Plays Analysis
    value_plays = {}
    for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
        pos_data = data[data['player_position_id'] == position].copy()
        if not pos_data.empty:
            pos_data['points_zscore'] = (pos_data['projected_points'] - pos_data['projected_points'].mean()) / pos_data['projected_points'].std()
            value_plays[position] = pos_data[pos_data['points_zscore'] > 1][
                ['player_name', 'salary', 'projected_points', 'points_zscore']
            ].to_dict('records')
    analysis['value_plays'] = value_plays

    # 2. Stack Analysis
    stacks = []
    qb_data = data[data['player_position_id'] == 'QB']
    receiver_data = data[data['player_position_id'].isin(['WR', 'TE'])]
    
    for _, qb in qb_data.iterrows():
        team_receivers = receiver_data[receiver_data['team'] == qb['team']]
        for _, receiver in team_receivers.iterrows():
            combined_salary = qb['salary'] + receiver['salary']
            if combined_salary <= 17500:  # 35% of salary cap
                stacks.append({
                    'qb': qb['player_name'],
                    'receiver': receiver['player_name'],
                    'total_salary': combined_salary,
                    'projected_points': qb['projected_points'] + receiver['projected_points'] * 1.1  # 10% correlation bonus
                })
    analysis['stacks'] = sorted(stacks, key=lambda x: x['projected_points'], reverse=True)

    # 3. Market Inefficiencies
    inefficiencies = {}
    for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
        pos_data = data[data['player_position_id'] == position].copy()
        if not pos_data.empty:
            pos_data['expected_points'] = pos_data['salary'].transform(
                lambda x: np.polyval(np.polyfit(pos_data['salary'], pos_data['projected_points'], 1), x)
            )
            pos_data['points_vs_expected'] = pos_data['projected_points'] - pos_data['expected_points']
            inefficiencies[position] = pos_data[
                pos_data['points_vs_expected'] > pos_data['points_vs_expected'].quantile(0.8)
            ][['player_name', 'salary', 'projected_points', 'points_vs_expected']].to_dict('records')
    analysis['inefficiencies'] = inefficiencies

    # 4. Tournament Plays
    tournament_plays = {}
    for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
        pos_data = data[data['player_position_id'] == position].copy()
        if not pos_data.empty:
            # Find high-upside, potentially low-owned players
            pos_data['ownership_proxy'] = pos_data['value_score'] / pos_data['value_score'].mean()
            tournament_plays[position] = pos_data[
                (pos_data['projected_points'] > pos_data['projected_points'].quantile(0.7)) &
                (pos_data['ownership_proxy'] < pos_data['ownership_proxy'].quantile(0.3))
            ][['player_name', 'salary', 'projected_points']].to_dict('records')
    analysis['tournament_plays'] = tournament_plays

    return analysis

def suggest_strategies_with_agent(data):
    """Generate strategy suggestions using the enhanced analysis."""
    analysis = analyze_data_for_strategy(data)
    
    # Format the analysis into a clear message
    message = []
    
    # 1. Value Plays
    message.append("🎯 TOP VALUE PLAYS BY POSITION:")
    for position, plays in analysis['value_plays'].items():
        if plays:
            message.append(f"\n{position} Standouts:")
            for play in plays[:3]:  # Top 3 per position
                message.append(
                    f"- {play['player_name']}: ${play['salary']:,} | "
                    f"{play['projected_points']:.1f} pts | "
                    f"Z-score: {play['points_zscore']:.2f}"
                )

    # 2. Stacking Opportunities
    message.append("\n\n🔄 OPTIMAL STACKING OPPORTUNITIES:")
    for stack in analysis['stacks'][:5]:  # Top 5 stacks
        message.append(
            f"- Stack: {stack['qb']} + {stack['receiver']}\n"
            f"  Combined Salary: ${stack['total_salary']:,} | "
            f"Projected: {stack['projected_points']:.1f} pts"
        )

    # 3. Market Inefficiencies
    message.append("\n\n💰 MARKET INEFFICIENCIES TO EXPLOIT:")
    for position, plays in analysis['inefficiencies'].items():
        if plays:
            for play in plays[:2]:  # Top 2 per position
                message.append(
                    f"- {play['player_name']} ({position}): "
                    f"Outperforming salary by {play['points_vs_expected']:.1f} pts"
                )

    # 4. Tournament Plays
    message.append("\n\n🎲 TOURNAMENT OPPORTUNITIES:")
    for position, plays in analysis['tournament_plays'].items():
        if plays:
            for play in plays[:2]:  # Top 2 per position
                message.append(
                    f"- {play['player_name']} ({position}): "
                    f"${play['salary']:,} | {play['projected_points']:.1f} pts"
                )

    return "\n".join(message)

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
def display_lineup(lineup, constraints, strategy_insights=""):
    """Display lineup with applied strategy insights"""
    # Keep existing lineup display code
    position_order = ['QB', 'RB1', 'RB2', 'WR1', 'WR2', 'WR3', 'TE', 'FLEX', 'DST']
    
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
    st.table(df)
    st.write(f"**Total Salary:** ${total_salary}")
    st.write(f"**Total Projected Points:** {total_projected_points:.2f}")

    # Add strategy insights if available
    if strategy_insights:
        applied_strategies = explain_lineup_with_architect(lineup, constraints, strategy_insights)
        if applied_strategies:
            st.markdown("**Applied Strategies:**")
            st.markdown(applied_strategies)

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

def create_fantasy_football_ui():
    st.title('Daily Fantasy Football Lineup Generator')
    
    # Strategy Suggestions Section
    with st.expander("View Strategy Suggestions", expanded=False):
        st.subheader("Strategy Analysis")
        strategy_insights = None
        if st.button("Generate Strategy Suggestions"):
            with st.spinner("Generating strategy suggestions..."):
                strategy_insights = suggest_strategies_with_agent(data)
                st.session_state.strategy_insights = strategy_insights
                st.markdown(strategy_insights)

    # Undervalued players section
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
            st.write("---")
    
    # User Input Section
    user_input = st.text_area('Enter your lineup requests:', '', height=75)
    
    col1, col2 = st.columns(2)
    with col1:
        num_lineups = st.number_input('Number of Lineups', min_value=1, max_value=150, value=1)
    with col2:
        max_exposure = st.slider('Maximum Player Exposure (%)', min_value=0, max_value=100, value=30)

    generate_button = st.button('Generate Lineup(s)')

    if generate_button:
        # Get fresh strategy insights if none exist
        if not strategy_insights:
            with st.spinner("Analyzing strategies..."):
                strategy_insights = suggest_strategies_with_agent(data)
        
        # Process constraints
        constraints = process_user_input_and_strategies(user_proxy, user_input_agent, user_input)
        constraints['num_lineups'] = num_lineups
        constraints['max_exposure'] = max_exposure / 100
        
        # Generate lineups
        lineups = optimizer_agent.generate_lineups(constraints)

        if not lineups:
            st.error("No lineups were generated.")
        else:
            for idx, lineup in enumerate(lineups):
                st.subheader(f'Lineup {idx + 1}')
                display_lineup(lineup, constraints, strategy_insights)

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
    
    # Check for recommended stacks
    if "OPTIMAL STACKING OPPORTUNITIES" in strategy_insights:
        stack_section = strategy_insights.split("OPTIMAL STACKING OPPORTUNITIES")[1].split("\n\n")[0]
        for team, players in team_players.items():
            if len(players) >= 2:
                if team.upper() in stack_section:
                    stack_players = [p['player_name'] for p in players]
                    projected = sum(float(p['projected_points']) for p in players)
                    applied_strategies.append(
                        f"• Using recommended {team.upper()} stack: {', '.join(stack_players)} "
                        f"(Proj: {projected:.1f}pts)"
                    )

    # Check for value plays
    if "TOP VALUE PLAYS" in strategy_insights:
        value_section = strategy_insights.split("TOP VALUE PLAYS")[1].split("\n\n")[0]
        for pos, player in lineup.items():
            if player and player['player_name'] in value_section.lower():
                applied_strategies.append(
                    f"• Value play: {player['player_name']} "
                    f"(${player['salary']:,}, Proj: {player['projected_points']:.1f}pts)"
                )

    # Check for tournament plays
    if "TOURNAMENT OPPORTUNITIES" in strategy_insights:
        tourney_section = strategy_insights.split("TOURNAMENT OPPORTUNITIES")[1].split("\n\n")[0]
        for pos, player in lineup.items():
            if player and player['player_name'] in tourney_section.lower():
                applied_strategies.append(f"• Tournament play: {player['player_name']}")

    return "\n".join(applied_strategies) if applied_strategies else ""

# Run the app
if __name__ == "__main__":
    create_fantasy_football_ui()