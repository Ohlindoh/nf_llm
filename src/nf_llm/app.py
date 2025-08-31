import os
import json
import pathlib
import pandas as pd
import streamlit as st
import httpx
from autogen import AssistantAgent, UserProxyAgent
from nf_llm.data_io import preprocess_data


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

    # Add a collapsible section for undervalued players
    with st.expander("View Most Undervalued Players", expanded=False):
        st.subheader("Most Undervalued Players")
        try:
            undervalued_players = get_undervalued_players()
            if undervalued_players:
                for position, players in undervalued_players.items():
                    st.write(f"**{position}**")
                    if players:  # Check if players list is not empty
                        df = pd.DataFrame(players)
                        st.dataframe(
                            df.style.format(
                                {
                                    "salary": "${:,.0f}",
                                    "projected_points": "{:.2f}",
                                    "value": "{:.4f}",
                                }
                            )
                        )
                    else:
                        st.write("No players found for this position")
                    st.write("---")  # Add a separator between positions
            else:
                st.error("Could not load undervalued players data")
        except Exception as e:
            st.error(f"Error loading undervalued players: {str(e)}")
            st.info("Make sure the API service is running on http://localhost:8000")

    user_input = st.text_area("Enter your lineup requests:", "", height=75)
    num_lineups = st.number_input(
        "Number of Lineups", min_value=1, max_value=150, value=1
    )
    max_exposure = st.slider(
        "Maximum Player Exposure (%)", min_value=0, max_value=100, value=65
    )

    generate_button = st.button("Generate Lineup(s)")

    if generate_button:
        # Process user input and strategies
        constraints = process_user_input_and_strategies(
            user_proxy, user_input_agent, user_input
        )
        constraints["num_lineups"] = num_lineups
        constraints["max_exposure"] = max_exposure / 100  # Convert to decimal

        lineups = call_optimiser(
            csv_path="data/merged_fantasy_football_data.csv",
            slate_id="DK‑NFL‑2025‑Week01",
            constraints=constraints,
        )

        if not lineups:
            st.error("No lineups were generated.")
        else:
            for idx, lineup in enumerate(lineups):
                st.subheader(f"Lineup {idx + 1}")
                display_lineup(lineup)

    if st.button("Reset"):
        st.experimental_rerun()


# Run the app
if __name__ == "__main__":
    create_fantasy_football_ui()
