import requests
import logging
import re
import csv
from typing import Optional, Dict, Any, List
import os
from datetime import datetime

from transformers.utils import clean_player_name

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONTESTS_URL = "https://www.draftkings.com/lobby/getcontests?sport=NFL"
DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{}/draftables"


def get_contest_by_type(contests: List[Dict[str, Any]], contest_type: str) -> Optional[Dict[str, Any]]:
    """Find a contest based on the specified type."""
    type_mapping = {
        "early": ["Early Only"],
        "afternoon": ["Afternoon Only"],
        "primetime": ["Primetime"],
        "main": ["Main", "Sun-Mon"],
        "thursday": ["Thu-Mon"],
        "sunday": ["Sunday Only"]
    }
    
    search_terms = type_mapping.get(contest_type.lower(), [contest_type])
    
    for contest in contests:
        if any(term.lower() in contest['n'].lower() for term in search_terms):
            return contest
    
    logger.error(f"No contest found for type: {contest_type}")
    return None

def collect_draftkings_data(contest_type: str) -> Optional[List[Dict[str, Any]]]:
    """Collect DraftKings data for NFL contests."""
    try:
        # Get contests
        response = requests.get(CONTESTS_URL)
        response.raise_for_status()
        contests = response.json().get('Contests', [])
        
        selected_contest = get_contest_by_type(contests, contest_type)
        
        if not selected_contest:
            return None
        
        draft_group_id = selected_contest['dg']
        logger.info(f"Using draft group ID: {draft_group_id} for '{contest_type}' contest")
        
        # Fetch draftables data
        response = requests.get(DRAFTABLES_URL.format(draft_group_id))
        response.raise_for_status()
        data = response.json()
        
        # Process the data
        processed_data = []
        for player in data['draftables']:
            processed_player = {
                'player_name': clean_player_name(player['displayName']),
                'original_name': player['displayName'],
                'player_team': player['teamAbbreviation'],
                'player_position': player['position'],
                'salary': player['salary'],
                'projected_points': player.get('projectedPoints', 0)
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

def main(contest_type: str):
    data = collect_draftkings_data(contest_type)
    if data:
        print(f"Successfully collected data for {len(data)} players")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dk_{contest_type}_{timestamp}.csv"
        write_to_csv(data, filename)
        print("Sample data:")
        for player in data[:5]:  # Print first 5 players as a sample
            print(player)
    else:
        print("Failed to collect DraftKings data")

if __name__ == "__main__":
    contest_type = input("Enter the contest type (e.g., 'Early', 'Afternoon', 'Primetime', 'Main', 'Thursday', 'Sunday'): ")
    main(contest_type)