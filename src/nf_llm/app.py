import json
import os
import pathlib

import httpx
import pandas as pd
import streamlit as st
from autogen import AssistantAgent, UserProxyAgent

_secret_path = pathlib.Path("/run/secrets/openai_api_key")
if not os.getenv("OPENAI_API_KEY") and _secret_path.exists():
    os.environ["OPENAI_API_KEY"] = _secret_path.read_text().strip()

# Initialize LLM configuration
llm_config = {
    "model": "gpt-5-mini",
    "api_key": os.environ.get("OPENAI_API_KEY")}

# API configuration - use environment variable or default to localhost
API_ROOT = os.getenv("API_BASE_URL", "http://localhost:8000")


def get_undervalued_players(top_n=5):
    payload = {"csv_path": "data/merged_fantasy_football_data.csv", "top_n": top_n}
    r = httpx.post(f"{API_ROOT}/undervalued-players", json=payload, timeout=60)
    if r.status_code != 200:
        st.error(f"API returned {r.status_code}: {r.json()['detail']}")
        return {}  # caller can handle empty dict gracefully

    return r.json()["players"]  # FastAPI guarantees this key


# Initialize agents
user_proxy = UserProxyAgent(
    name="UserProxy", human_input_mode="NEVER", max_consecutive_auto_reply=0
)

user_input_agent = AssistantAgent(
    name="UserInputAgent",
    llm_config=llm_config,
    system_message="""\
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
    """,
)


def call_optimiser(csv_path: str, slate_id: str, constraints: dict):
    payload = {
        "csv_path": csv_path,
        "slate_id": slate_id,
        "constraints": constraints,
    }
    r = httpx.post(f"{API_ROOT}/optimise", json=payload, timeout=60)
    if r.status_code != 200:
        st.error(f"API returned {r.status_code}: {r.json()['detail']}")
        return None  # caller can handle None gracefully

    return r.json()["lineups"]  # FastAPI guarantees this key


# Function to process user input and strategies
def process_user_input_and_strategies(user_proxy, user_input_agent, user_input):
    if not user_input.strip():
        return {}
    else:
        user_input_agent.reset()
        user_proxy.send(user_input, user_input_agent, request_reply=True)
        response = user_input_agent.last_message()["content"]
        try:
            constraints = json.loads(response)
        except json.JSONDecodeError:
            constraints = {}
        return constraints


# Function to display lineup
def display_lineup(lineup):
    # Define the desired order of positions
    position_order = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]

    # Build the DataFrame with positions in the specified order
    lineup_data = []
    total_salary = 0
    total_projected_points = 0
    for position in position_order:
        player = lineup.get(position)
        if player:
            salary = player["salary"]
            projected_points = player["projected_points"]
            lineup_data.append(
                {
                    "Position": position,
                    "Player": player["player_name"],
                    "Team": player["team"].upper(),
                    "Projected Points": projected_points,
                    "Salary": f"${salary}",
                }
            )
            total_salary += salary
            total_projected_points += projected_points
        else:
            lineup_data.append(
                {
                    "Position": position,
                    "Player": "",
                    "Team": "",
                    "Projected Points": "",
                    "Salary": "",
                }
            )

    df = pd.DataFrame(lineup_data)

    # Display the lineup table
    st.table(df)

    # Display total salary and projected points
    st.write(f"**Total Salary:** ${total_salary}")
    st.write(f"**Total Projected Points:** {total_projected_points:.2f}")


# Create UI using Streamlit
def create_fantasy_football_ui():
    st.title("Daily Fantasy Football Lineup Generator")
    
    # Create tabs for different sections
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Players", 
        "Optimizer", 
        "Lineups", 
        "Games & Odds", 
        "Projections", 
        "Admin"
    ])
    
    with tab1:
        show_players_tab()
        
    with tab2:
        show_optimizer_tab()
        
    with tab3:
        show_lineups_tab()
        
    with tab4:
        show_games_odds_tab()
        
    with tab5:
        show_projections_tab()
        
    with tab6:
        show_admin_tab()


def show_players_tab():
    """Display the Players tab with scouting table and undervalued players panel."""
    st.header("Player Scouting")
    
    # Load player data
    try:
        player_data = pd.read_csv("data/merged_fantasy_football_data.csv")
        if player_data is None or player_data.empty:
            st.info("No player data available. Please check the data source.")
            return
    except Exception as e:
        st.error(f"Error loading player data: {str(e)}")
        return
    
    # Add compact filter bar at the top
    st.subheader("Filters")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        positions = ["All"] + sorted(player_data["player_position_id"].unique())
        selected_position = st.selectbox("Position", positions, index=0)
        
    with col2:
        teams = ["All"] + sorted(player_data["player_team_id"].unique())
        selected_team = st.selectbox("Team", teams, index=0)
        
    with col3:
        # Projected points range filter
        min_points = int(player_data["projected_points"].min())
        max_points = int(player_data["projected_points"].max())
        points_range = st.slider("Projected Points Range", min_points, max_points, 
                                (min_points, max_points))
    
    # Apply filters
    filtered_data = player_data.copy()
    if selected_position != "All":
        filtered_data = filtered_data[filtered_data["player_position_id"] == selected_position]
    if selected_team != "All":
        filtered_data = filtered_data[filtered_data["player_team_id"] == selected_team]
    filtered_data = filtered_data[
        (filtered_data["projected_points"] >= points_range[0]) & 
        (filtered_data["projected_points"] <= points_range[1])
    ]
    
    # Add a section for undervalued players with lazy loading
    st.subheader("Most Undervalued Players")
    st.caption("Players with the highest projected points relative to their salary")
    
    # Add a button to fetch undervalued players on demand
    if st.button("Find Undervalued Players"):
        try:
            undervalued_players = get_undervalued_players()
            if undervalued_players:
                # Create tabs for different positions
                position_tabs = st.tabs(list(undervalued_players.keys()))
                for i, (position, players) in enumerate(undervalued_players.items()):
                    with position_tabs[i]:
                        if players:  # Check if players list is not empty
                            df = pd.DataFrame(players)
                            st.dataframe(
                                df.style.format(
                                    {
                                        "salary": "${:,.0f}",
                                        "projected_points": "{:.2f}",
                                        "value": "{:.4f}",
                                    }
                                ),
                                use_container_width=True
                            )
                        else:
                            st.write("No players found for this position")
            else:
                st.error("Could not load undervalued players data")
        except Exception as e:
            st.error(f"Error loading undervalued players: {str(e)}")
            st.info("Make sure the API service is running on http://localhost:8000")
    
    # Display filtered player data with pagination
    st.subheader(f"Players ({len(filtered_data)} found)")
    
    # Add pagination controls
    page_size = st.selectbox("Players per page", [10, 25, 50, 100], index=1)
    total_pages = len(filtered_data) // page_size + (1 if len(filtered_data) % page_size > 0 else 0)
    
    if total_pages > 1:
        page_number = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
        start_idx = (page_number - 1) * page_size
        end_idx = start_idx + page_size
        paginated_data = filtered_data.iloc[start_idx:end_idx]
        st.dataframe(paginated_data, use_container_width=True)
        st.caption(f"Showing {start_idx+1}-{min(end_idx, len(filtered_data))} of {len(filtered_data)} players")
    else:
        st.dataframe(filtered_data, use_container_width=True)


def show_optimizer_tab():
    """Display the Optimizer tab with constraint inputs and lineup generation."""
    st.header("Lineup Optimizer")
    
    # Constraint input section
    st.subheader("Constraints")
    col1, col2 = st.columns(2)
    
    with col1:
        user_input = st.text_area("Enter your lineup requests:", "", height=100)
        num_lineups = st.number_input(
            "Number of Lineups", min_value=1, max_value=150, value=1
        )
        
    with col2:
        max_exposure = st.slider(
            "Maximum Player Exposure (%)", min_value=0, max_value=100, value=65
        )
        # Add a visual divider
        st.markdown("---")
        st.caption("Click 'Generate Lineups' to create optimized lineups based on your constraints")
    
    # Buttons for generating and resetting
    col1, col2 = st.columns(2)
    with col1:
        generate_button = st.button("Generate Lineups", type="primary", use_container_width=True)
    with col2:
        if st.button("Reset", use_container_width=True):
            st.experimental_rerun()
    
    # Results section
    if generate_button:
        st.subheader("Optimization Results")
        # Process user input and strategies
        constraints = process_user_input_and_strategies(
            user_proxy, user_input_agent, user_input
        )
        constraints["num_lineups"] = num_lineups
        constraints["max_exposure"] = max_exposure / 100  # Convert to decimal
        
        with st.spinner("Generating lineups..."):
            lineups = call_optimiser(
                csv_path="data/merged_fantasy_football_data.csv",
                slate_id="DK‑NFL‑2025‑Week01",
                constraints=constraints,
            )
        
        if not lineups:
            st.error("No lineups were generated.")
        else:
            # Display lineups in tabs
            lineup_tabs = st.tabs([f"Lineup {i+1}" for i in range(len(lineups))])
            for i, lineup in enumerate(lineups):
                with lineup_tabs[i]:
                    display_lineup(lineup)


def show_lineups_tab():
    """Display the Lineups tab with saved lineups."""
    st.header("Saved Lineups")
    st.info("This section will display your saved lineups. Feature coming soon.")


def show_games_odds_tab():
    """Display the Games & Odds tab with matchups."""
    st.header("Games & Odds")
    st.info("This section will display game matchups, odds, and kickoff times. Feature coming soon.")


def show_projections_tab():
    """Display the Projections tab with projection sources comparison."""
    st.header("Projections")
    
    # Create sample projection sources comparison data
    projections_data = {
        "Player": ["Josh Allen", "Christian McCaffrey", "Justin Jefferson", "Tyreek Hill", "Travis Kelce"],
        "Position": ["QB", "RB", "WR", "WR", "TE"],
        "Team": ["BUF", "SF", "MIN", "MIA", "KC"],
        "ESPN": [22.5, 18.5, 19.2, 17.8, 15.2],
        "Yahoo": [21.8, 19.2, 18.5, 18.2, 14.8],
        "NFL.com": [23.1, 17.9, 19.8, 17.5, 15.5],
        "FantasyPros": [22.2, 18.8, 19.0, 18.0, 15.0],
        "Consensus": [22.4, 18.6, 19.1, 17.9, 15.1]
    }
    
    df = pd.DataFrame(projections_data)
    st.dataframe(df, use_container_width=True)
    
    # Add a visual divider and explanation
    st.markdown("---")
    st.caption("This table compares projections from different sources for key players. "
              "The 'Consensus' column shows the average projection across all sources.")
    
    # Add a section for projection analysis
    st.subheader("Projection Analysis")
    st.info("Advanced projection analysis tools will be added in a future update.")


def show_admin_tab():
    """Display the Admin tab with refresh options."""
    st.header("Admin")
    st.info("This section will display refresh buttons and model information. Feature coming soon.")


def create_espn_team_ui():
    """Simple interface for viewing a user's ESPN fantasy team."""
    st.title("ESPN Team Viewer")
    league_id = st.text_input("League ID", "")
    # Remove year input and use current year automatically
    swid = st.text_input("SWID")
    espn_s2 = st.text_input("ESPN_S2")

    if st.button("Load Team"):
        try:
            from nf_llm.fantasy_football.espn import get_user_team
            import datetime
            
            current_year = datetime.datetime.now().year

            roster = get_user_team(int(league_id), current_year, swid, espn_s2)
            if roster:
                st.dataframe(pd.DataFrame(roster))
            else:
                st.info("No players found for this team.")
        except Exception as e:  # pragma: no cover - UI feedback only
            st.error(f"Failed to load team: {e}")


def main():
    page = st.sidebar.radio("Mode", ["DFS", "ESPN"])
    if page == "DFS":
        create_fantasy_football_ui()
    else:
        create_espn_team_ui()


# Run the app
if __name__ == "__main__":
    main()
