import datetime
import json
import os
import pathlib

import httpx
import pandas as pd
import streamlit as st
from autogen import AssistantAgent, UserProxyAgent
from nf_llm.fantasy_football.espn import _find_user_team, get_league_rosters, load_league
from nf_llm.fantasy_football.espn_optimizer import build_optimal_lineup

# Try multiple methods to get the API key
_secret_path = pathlib.Path("/run/secrets/openai_api_key")
if not os.getenv("OPENAI_API_KEY"):
    if _secret_path.exists():
        os.environ["OPENAI_API_KEY"] = _secret_path.read_text().strip()
    else:
        # Fallback for development - will error if not set
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            st.error("⚠️ OPENAI_API_KEY not found. Set it in your environment before running docker-compose.")
            st.stop()

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
        You are an expert DFS (Daily Fantasy Sports) assistant that processes user requests for fantasy football lineups.
        Parse the user's natural language input and convert it into a structured JSON format for lineup optimization.
        
        LINEUP TYPES:
        - Cash Game: Conservative lineups for 50/50s and double-ups. Focus on high-floor, consistent players.
        - GPP (Tournament): High-risk/high-reward lineups for large tournaments. Focus on high-ceiling, volatile players.
        - Balanced: Mix of safe and upside plays.
        
        STRATEGY PARAMETERS:
        1. lineup_type: "cash", "gpp", or "balanced"
        2. variance_preference: "low" (cash), "high" (gpp), or "medium" (balanced)
        3. ownership_strategy: "contrarian" (fade chalk), "balanced", or "chalk" (popular plays)
        4. correlation_strategy: "max" (heavy stacking), "moderate", or "none"
        5. floor_weight: 0.0 to 1.0 (how much to prioritize floor vs ceiling)
        
        EXAMPLES:
        
        Input: "Create a cash lineup"
        Output: {
            "lineup_type": "cash",
            "variance_preference": "low",
            "floor_weight": 0.8,
            "ownership_strategy": "balanced",
            "correlation_strategy": "moderate"
        }
        
        Input: "Build a GPP lineup with contrarian plays"
        Output: {
            "lineup_type": "gpp",
            "variance_preference": "high",
            "floor_weight": 0.2,
            "ownership_strategy": "contrarian",
            "correlation_strategy": "max"
        }
        
        Input: "I want a safe lineup with consistent players, no risky picks"
        Output: {
            "lineup_type": "cash",
            "variance_preference": "low",
            "floor_weight": 0.9,
            "ownership_strategy": "chalk",
            "correlation_strategy": "none"
        }
        
        Input: "Create 5 tournament lineups with different stacks"
        Output: {
            "num_lineups": 5,
            "lineup_type": "gpp",
            "variance_preference": "high",
            "floor_weight": 0.3,
            "correlation_strategy": "max",
            "diversify_stacks": true
        }
        
        Input: "I want Justin Jefferson and avoid Jets players"
        Output: {
            "must_include": ["justinjefferson"],
            "avoid_teams": ["nyj"]
        }
        
        Input: "Focus on players with high floor for cash games"
        Output: {
            "lineup_type": "cash",
            "variance_preference": "low",
            "floor_weight": 1.0,
            "min_projected_points": 10.0
        }
        
        Input: "Create a balanced lineup with some upside"
        Output: {
            "lineup_type": "balanced",
            "variance_preference": "medium",
            "floor_weight": 0.5,
            "ownership_strategy": "balanced"
        }
        
        Input: "Stack Chiefs players for GPP"
        Output: {
            "lineup_type": "gpp",
            "stack_teams": ["kc"],
            "correlation_strategy": "max",
            "variance_preference": "high"
        }
        
        Input: "Limit Patrick Mahomes to 50% exposure"
        Output: {
            "player_exposure_limits": {"patrickmahomes": 0.5}
        }
        
        Input: "Generate 20 unique lineups for a large tournament"
        Output: {
            "num_lineups": 20,
            "lineup_type": "gpp",
            "variance_preference": "high",
            "unique_lineups": true,
            "diversify_stacks": true
        }
        
        ADDITIONAL CONSTRAINTS:
        - min_projected_points: Minimum projected points for any player
        - max_salary_per_player: Maximum salary for any single player
        - min_games: Minimum number of different games to use players from
        - max_players_per_team: Maximum players from same team
        - unique_lineups: Ensure all lineups are different
        - diversify_stacks: Use different team stacks across multiple lineups
        
        If the input doesn't contain specific constraints, infer reasonable defaults based on the lineup type.
        Always provide valid JSON output.
    """,
)


def call_optimiser(csv_path: str, constraints: dict):
    payload = {
        "csv_path": csv_path,
        "constraints": constraints,
    }
    r = httpx.post(f"{API_ROOT}/optimise", json=payload, timeout=None)
    if r.status_code != 200:
        st.error(f"API returned {r.status_code}: {r.json()['detail']}")
        return None, None  # caller can handle None gracefully

    data = r.json()
    return data["lineups"], data.get("slate_id")


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
    
    # Add refresh button and file info at the top
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Data", key="refresh_players"):
            st.cache_data.clear()
            st.rerun()
    
    # Load player data
    try:
        csv_path = "data/merged_fantasy_football_data.csv"
        player_data = pd.read_csv(csv_path)
        
        # Show file modification time
        try:
            import os
            from datetime import datetime
            mtime = os.path.getmtime(csv_path)
            file_time = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            with col1:
                st.caption(f"Data last modified: {file_time}")
        except:
            pass
        
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
        positions = ["All"] + sorted([pos for pos in player_data["player_position_id"].unique() if pd.notna(pos)])
        selected_position = st.selectbox("Position", positions, index=0)
        
    with col2:
        teams = ["All"] + sorted([team for team in player_data["player_team_id"].unique() if pd.notna(team)])
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
        # Add QB diversity controls
        st.markdown("**QB Diversity Settings**")
        qb_diversity_mode = st.selectbox(
            "QB Diversity Mode",
            ["rotate", "limit", "none"],
            index=0,
            help="rotate: Force different QBs each lineup | limit: Enforce max QB exposure | none: No QB restrictions"
        )
        max_qb_exposure = st.slider(
            "Maximum QB Exposure (%)", 
            min_value=5, 
            max_value=50, 
            value=15,
            help="Maximum percentage of lineups a single QB can appear in"
        )
        # Add a visual divider
        st.markdown("---")
        st.caption("Click 'Generate Lineups' to create optimized lineups based on your constraints")
    
    # Buttons for generating and resetting
    col1, col2 = st.columns(2)
    with col1:
        generate_button = st.button("Generate Lineups", type="primary", use_container_width=True, key="generate_lineups_btn")
    with col2:
        if st.button("Reset", use_container_width=True, key="reset_btn"):
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
        constraints["max_qb_exposure"] = max_qb_exposure / 100  # Convert to decimal
        constraints["qb_diversity_mode"] = qb_diversity_mode
        
        # Display the strategy being used
        if constraints:
            lineup_type = constraints.get("lineup_type", "balanced")
            if lineup_type == "cash":
                st.info("🛡️ **Cash Game Strategy**: Optimizing for consistent, high-floor players with lower variance")
            elif lineup_type == "gpp":
                st.info("🚀 **GPP/Tournament Strategy**: Optimizing for high-ceiling players with upside potential")
            else:
                st.info("⚖️ **Balanced Strategy**: Mixing safe plays with upside potential")
            
            # Show additional strategy details if present
            strategy_details = []
            if "variance_preference" in constraints:
                strategy_details.append(f"Variance: {constraints['variance_preference']}")
            if "floor_weight" in constraints:
                strategy_details.append(f"Floor weight: {constraints['floor_weight']:.1%}")
            if "correlation_strategy" in constraints:
                strategy_details.append(f"Correlation: {constraints['correlation_strategy']}")
            if "ownership_strategy" in constraints:
                strategy_details.append(f"Ownership: {constraints['ownership_strategy']}")
            
            if strategy_details:
                st.caption(" • ".join(strategy_details))
        
        with st.spinner("Generating lineups..."):
            lineups, slate_id = call_optimiser(
                csv_path="data/merged_fantasy_football_data.csv",
                constraints=constraints,
            )

        if not lineups:
            st.error("No lineups were generated.")
        else:
            # Store lineups and slate_id in session state for export functionality
            st.session_state["current_lineups"] = lineups
            st.session_state["current_slate_id"] = slate_id
            
            # Display lineups in tabs
            lineup_tabs = st.tabs([f"Lineup {i+1}" for i in range(len(lineups))])
            for i, lineup in enumerate(lineups):
                with lineup_tabs[i]:
                    display_lineup(lineup)
            
    # Export button - outside the generate_button block so it persists
    if "current_lineups" in st.session_state and st.session_state["current_lineups"]:
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Export to CSV", type="primary", key="export_csv_btn"):
                lineups = st.session_state["current_lineups"]
                slate_id = st.session_state.get("current_slate_id", "lineups")
                
                # Create CSV with player IDs
                csv_data = []
                csv_data.append(["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"])
                
                for lineup in lineups:
                    row = []
                    for pos in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]:
                        player = lineup.get(pos, {})
                        # Use draftableId for DraftKings CSV upload (this is what DK expects)
                        if isinstance(player, dict):
                            # DraftKings uses draftableId, not dk_player_id
                            player_id = player.get("draftable_id") or player.get("dk_player_id") or ""
                            # Convert to int if it's a float to remove decimal
                            if player_id and isinstance(player_id, (int, float)):
                                player_id = str(int(player_id))
                            else:
                                player_id = str(player_id) if player_id else ""
                        else:
                            player_id = ""
                        row.append(player_id)
                    csv_data.append(row)
                
                # Convert to CSV string
                csv_content = "\n".join([",".join(row) for row in csv_data])
                
                # Store in session state for download button
                st.session_state["csv_content"] = csv_content
                st.session_state["csv_filename"] = f"lineups_{slate_id}.csv"
        
        # Show download button if CSV is ready
        if "csv_content" in st.session_state:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.download_button(
                    "⬇️ Download CSV",
                    data=st.session_state["csv_content"],
                    file_name=st.session_state["csv_filename"],
                    mime="text/csv",
                    key="download_csv_btn"
                )


def show_lineups_tab():
    """Display queued lineups and allow DraftKings CSV export."""
    st.header("DraftKings Export")

    salaries_dir = pathlib.Path(os.getenv("DK_SALARIES_DIR", "data/raw/dk_salaries"))
    slate_options = sorted(p.stem.replace("_raw", "") for p in salaries_dir.glob("*_raw.csv"))
    if slate_options:
        slate_id = st.selectbox("Slate", slate_options)
    else:
        slate_id = st.text_input("Slate ID")

    lineups = st.session_state.get("dk_lineups", [])
    if not lineups:
        st.info("No lineups queued for export.")
        return

    headers = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
    df = pd.DataFrame(lineups, columns=headers)
    st.table(df)

    if st.button("Download DraftKings CSV"):
        payload = {"slate_id": slate_id, "lineups": lineups}
        try:
            r = httpx.post(f"{API_ROOT}/export/dk_csv", json=payload, timeout=60)
        except Exception as err:  # pragma: no cover - network failures
            st.error(f"API request failed: {err}")
            return

        if r.status_code != 200:
            st.error(f"API returned {r.status_code}: {r.text}")
            return

        invalid_header = r.headers.get("X-Invalid-Lineups", "")
        invalid_indices = [i for i in invalid_header.split(",") if i]
        invalid_count = len(invalid_indices)
        valid_count = len(lineups) - invalid_count

        st.download_button(
            "Download DK CSV",
            data=r.content,
            file_name="dk_lineups.csv",
            mime="text/csv",
        )
        st.caption(
            f"{valid_count}/{len(lineups)} lineups valid; {invalid_count} rejected (bad IDs)."
        )


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
    """Interface for viewing ESPN fantasy data including full league rosters."""
    st.title("ESPN Team Viewer")
    league_id = st.text_input("League ID", "")
    # Remove year input and use current year automatically
    swid = st.text_input("SWID")
    espn_s2 = st.text_input("ESPN_S2")
    current_year = datetime.datetime.now().year

    tab_my_team, tab_league_rosters = st.tabs(["My Team", "League Rosters"])

    with tab_my_team:
        st.subheader("Your Team & Recommendations")

        if st.button("Load My Team", key="load_my_team"):
            if not league_id or not swid or not espn_s2:
                st.error("Please provide League ID, SWID, and ESPN_S2 to load your team.")
                return

            try:
                numeric_league_id = int(league_id)
            except ValueError:
                st.error("League ID must be a number.")
                return

            try:
                league = load_league(
                    league_id=numeric_league_id,
                    year=current_year,
                    swid=swid,
                    espn_s2=espn_s2,
                )
            except Exception as e:  # pragma: no cover - UI feedback only
                st.error(f"Failed to load league: {e}")
                return

            team = _find_user_team(league, swid)
            if team is None:
                st.error("Could not determine team for provided credentials")
                return

            roster = [
                {
                    "name": getattr(p, "name", ""),
                    "position": getattr(p, "position", ""),
                    "proTeam": getattr(p, "proTeam", ""),
                }
                for p in getattr(team, "roster", [])
            ]

            st.subheader("Roster")
            if roster:
                st.dataframe(pd.DataFrame(roster))
            else:
                st.info("No players found for this team.")

            result = build_optimal_lineup(team, league)
            st.subheader("Optimal Lineup")
            st.json(result["lineup"])

            st.subheader("Suggested Pickups")
            if result["pickups"]:
                st.json(result["pickups"])
            else:
                st.info("No significant pickups found.")

    with tab_league_rosters:
        st.subheader("Browse All Team Rosters")
        st.caption("View every roster in your ESPN league in one place.")

        if st.button("Load League Rosters", key="load_league_rosters"):
            if not league_id or not swid or not espn_s2:
                st.error("Please provide League ID, SWID, and ESPN_S2 to browse rosters.")
                return

            try:
                numeric_league_id = int(league_id)
            except ValueError:
                st.error("League ID must be a number.")
                return

            try:
                rosters = get_league_rosters(
                    league_id=numeric_league_id,
                    year=current_year,
                    swid=swid,
                    espn_s2=espn_s2,
                )
            except Exception as e:  # pragma: no cover - UI feedback only
                st.error(f"Failed to load league rosters: {e}")
                return

            if not rosters:
                st.info("No rosters were returned for this league.")
                return

            team_labels = [
                f"{team['team_name'] or 'Team'} (ID {team['team_id']})" for team in rosters
            ]
            selected_team_label = st.selectbox(
                "Select a team to view its roster", team_labels, key="roster_team_select"
            )

            selected_index = team_labels.index(selected_team_label)
            selected_team = rosters[selected_index]

            st.markdown(
                f"**Owners:** {', '.join(selected_team['owners']) if selected_team['owners'] else 'Unknown'}"
            )
            st.dataframe(pd.DataFrame(selected_team["roster"]))

            with st.expander("View all team rosters"):
                for team_label, team_data in zip(team_labels, rosters):
                    st.markdown(f"### {team_label}")
                    st.markdown(
                        f"**Owners:** {', '.join(team_data['owners']) if team_data['owners'] else 'Unknown'}"
                    )
                    st.dataframe(pd.DataFrame(team_data["roster"]))


def main():
    page = st.sidebar.radio("Mode", ["DFS", "ESPN"])
    if page == "DFS":
        create_fantasy_football_ui()
    else:
        create_espn_team_ui()


# Run the app
if __name__ == "__main__":
    main()
