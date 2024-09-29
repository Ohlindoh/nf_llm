import requests
import logging
import re
import csv
from typing import Optional, Dict, Any, List
import os
import argparse

from collectors.utils import clean_player_name

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONTESTS_URL = "https://www.draftkings.com/lobby/getcontests?sport=NFL"
DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{}/draftables"


def get_contest_by_type(contests: List[Dict[str, Any]], contest_type: str) -> Optional[Dict[str, Any]]:
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
            contest_name = contest.get('n', '').lower()
            if any(term in contest_name for term in type_mapping[contest_type]):
                return contest
        
        # Fallback for exact match if not in type_mapping
        if contest_type in contest.get('n', '').lower():
            return contest
    
    logger.error(f"No contest found for type: {contest_type}")
    return None


def collect_draftkings_data(contest_type: str, draft_group_id: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
    """Collect DraftKings data for NFL contests."""
    try:
        if draft_group_id is None:
            # Get contests
            response = requests.get(CONTESTS_URL)
            response.raise_for_status()
            contests = response.json().get('Contests', [])
            
            selected_contest = get_contest_by_type(contests, contest_type)
            
            if not selected_contest:
                logger.error(f"Could not find contest for type '{contest_type}'")
                return None
            
            draft_group_id = selected_contest['dg']
            logger.info(f"Using draft group ID: {draft_group_id} for '{contest_type}' contest")
        else:
            logger.info(f"Using provided draft group ID: {draft_group_id}")
        
        # Fetch draftables data
        response = requests.get(DRAFTABLES_URL.format(draft_group_id))
        response.raise_for_status()
        data = response.json()
        
        # Process the data
        processed_data = []
        for player in data['draftables']:
            processed_player = {
                'player_name': clean_player_name(player['displayName']),
                'salary': player['salary'],
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


def write_to_csv(data: List[Dict[str, Any]], filename: str = 'dk.csv'):
    """Write the processed data to a CSV file."""
    if not data:
        logger.error("No data to write to CSV")
        return

    output_dir = 'data'
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    fieldnames = data[0].keys()
    
    try:
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
        logger.info(f"Successfully wrote data to {filepath}")
    except IOError as e:
        logger.error(f"Error writing to CSV file: {e}")


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
    parser = argparse.ArgumentParser(description="Collect DraftKings data for NFL contests.")
    parser.add_argument("--contest_type", type=str, default="Main",
                        help="Contest type (e.g., 'Early', 'Afternoon', 'Primetime', 'Main', 'Thursday', 'Sunday')")
    parser.add_argument("--draft_group_id", type=int, default=None,
                        help="Draft group ID (overrides contest type if provided)")
    args = parser.parse_args()

    main(args.contest_type, args.draft_group_id)
