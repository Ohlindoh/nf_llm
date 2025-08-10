import requests
import logging
import re
import csv
from typing import Optional, Dict, Any, List
import os
import argparse
from pathlib import Path
import datetime as dt
import pandas as pd


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CONTESTS_URL = "https://www.draftkings.com/lobby/getcontests?sport=NFL"
DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{}/draftables"


def get_contest_by_type(
    contests: List[Dict[str, Any]], contest_type: str
) -> Optional[Dict[str, Any]]:
    """Find a contest based on the specified type."""
    contest_type = contest_type.lower()

    type_mapping = {
        "early": ["early only"],
        "afternoon": ["afternoon only"],
        "primetime": ["primetime"],
        "main": ["main", "sun-mon"],
        "thursday": ["thu-mon"],
        "sunday": ["sunday only"],
    }

    for contest in contests:
        # Check for Featured contest
        if contest_type == "featured":
            if contest.get("dg") == 113472 or contest.get("DraftGroupId") == 113472:
                return contest

        # Check for other contest types
        if contest_type in type_mapping:
            contest_name = contest.get("n", "").lower()
            if any(term in contest_name for term in type_mapping[contest_type]):
                return contest

        # Fallback for exact match if not in type_mapping
        if contest_type in contest.get("n", "").lower():
            return contest

    logger.error(f"No contest found for type: {contest_type}")
    return None


def write_raw_dk(df, slate_id: str):
    """Save raw DraftKings data snapshot by slate."""
    out = Path(f"data/raw/dk_salaries/{slate_id}_raw.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"[dk] raw snapshot → {out.resolve()}  ({len(df)} rows)")


def generate_slate_id(contest_type: str, draft_group_id: int) -> str:
    """Generate a slate ID based on contest info and current date."""
    # Get current date for week calculation
    now = dt.datetime.now()
    year = now.year
    
    # Simple week calculation (could be refined)
    week_of_year = now.isocalendar()[1]
    
    # Create slate ID
    slate_id = f"DK_{contest_type.upper()}_{year}W{week_of_year:02d}_{draft_group_id}"
    return slate_id


def collect_draftkings_data(
    contest_type: str, draft_group_id: Optional[int] = None
) -> Optional[List[Dict[str, Any]]]:
    """Collect DraftKings data for NFL contests."""
    try:
        if draft_group_id is None:
            # Get contests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.draftkings.com/'
            }
            response = requests.get(CONTESTS_URL, headers=headers)
            response.raise_for_status()
            contests = response.json().get("Contests", [])

            selected_contest = get_contest_by_type(contests, contest_type)

            if not selected_contest:
                logger.error(f"Could not find contest for type '{contest_type}'")
                return None

            draft_group_id = selected_contest["dg"]
            logger.info(
                f"Using draft group ID: {draft_group_id} for '{contest_type}' contest"
            )
        else:
            logger.info(f"Using provided draft group ID: {draft_group_id}")

        # Fetch draftables data with proper headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.draftkings.com/',
            'Origin': 'https://www.draftkings.com'
        }
        
        draftables_url = DRAFTABLES_URL.format(draft_group_id)
        logger.info(f"Requesting URL: {draftables_url}")
        
        response = requests.get(draftables_url, headers=headers)
        logger.info(f"Response status code: {response.status_code}")
        
        if response.status_code == 404:
            logger.error(f"Draft group {draft_group_id} not found. This could mean:")
            logger.error("1. The draft group ID is invalid or expired")
            logger.error("2. The contest is not yet available for drafting")
            logger.error("3. The contest has already closed")
            logger.error("4. The API endpoint structure has changed")
            return None
            
        response.raise_for_status()
        data = response.json()

        # DEBUG: Save raw data preview to see all available fields
        if data.get("draftables"):
            raw_data = []
            for player in data["draftables"]:
                raw_data.append(player)
            
            if raw_data:
                df_raw = pd.DataFrame(raw_data)
                
                # 1) Save a wider preview without dropping columns
                df_raw.to_csv("data/dk_raw_preview.csv", index=False)
                
                # 2) Print the available columns so we see what's there
                print("[dk] available columns:", list(df_raw.columns)[:20], "...")
                print(f"[dk] total columns: {len(df_raw.columns)}")

        # Process the data
        processed_data = []
        seen_players = set()  # Track unique players to avoid duplicates
        
        slate_id = generate_slate_id(contest_type, draft_group_id)
        write_raw_dk(pd.DataFrame(data["draftables"]), slate_id)

        for player in data["draftables"]:
            player_key = (player["displayName"], player["salary"])
            
            # Skip if we've already seen this exact player/salary combination
            if player_key in seen_players:
                continue
                
            seen_players.add(player_key)
            processed_player = {
                "player_name": player["displayName"],
                "salary": player["salary"],
                # Include other fields as needed
            }
            processed_data.append(processed_player)

        logger.info(f"Successfully processed data for {len(processed_data)} players")
        return processed_data

    except requests.RequestException as e:
        logger.error(f"Error fetching data from DraftKings: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

    return None


def write_to_csv(data: List[Dict[str, Any]], filename: str = "dk.csv"):
    """Write the processed data to a CSV file."""
    if not data:
        logger.error("No data to write to CSV")
        return

    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    fieldnames = data[0].keys()

    try:
        with open(filepath, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
        logger.info(f"Successfully wrote data to {filepath}")
    except IOError as e:
        logger.error(f"Error writing to CSV file: {e}")


def list_available_contests():
    """List all available contests and their draft group IDs for debugging."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.draftkings.com/'
        }
        response = requests.get(CONTESTS_URL, headers=headers)
        response.raise_for_status()
        contests = response.json().get("Contests", [])
        
        print(f"Found {len(contests)} available contests:")
        print("-" * 80)
        
        for contest in contests[:20]:  # Show first 20 contests
            draft_group_id = contest.get("dg", "N/A")
            contest_name = contest.get("n", "Unknown")
            entry_fee = contest.get("a", "N/A")
            entries = contest.get("m", "N/A")
            
            print(f"Draft Group ID: {draft_group_id}")
            print(f"Contest Name: {contest_name}")
            print(f"Entry Fee: ${entry_fee}")
            print(f"Max Entries: {entries}")
            print("-" * 40)
            
    except Exception as e:
        logger.error(f"Error fetching contests: {e}")


def main(contest_type: str, draft_group_id: Optional[int] = None):
    data = collect_draftkings_data(contest_type, draft_group_id)
    if data:
        print(f"Successfully collected data for {len(data)} players")
        filename = "dk.csv"
        write_to_csv(data, filename)
        print("Sample data:")
        for player in data[:5]:  # Print first 5 players as a sample
            print(player)
    else:
        print("Failed to collect DraftKings data")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect DraftKings data for NFL contests."
    )
    parser.add_argument(
        "--contest_type",
        type=str,
        default="Main",
        help="Contest type (e.g., 'Early', 'Afternoon', 'Primetime', 'Main', 'Thursday', 'Sunday')",
    )
    parser.add_argument(
        "--draft_group_id",
        type=int,
        default=None,
        help="Draft group ID (overrides contest type if provided)",
    )
    parser.add_argument(
        "--list_contests",
        action="store_true",
        help="List all available contests and their draft group IDs",
    )
    args = parser.parse_args()

    if args.list_contests:
        list_available_contests()
    else:
        main(args.contest_type, args.draft_group_id)
