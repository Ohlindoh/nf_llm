import requests
import logging
import re
import csv
from typing import Optional, Dict, Any, Literal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONTESTS_URL = "https://api.draftkings.com/contests/v1/contests?sport=NFL"
DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{}/draftables"

ScheduleType = Literal["Thu-Mon", "Sunday", "Sun-Mon", "Fri-Mon"]

def clean_player_name(name: str) -> str:
    """Clean player name for consistent matching."""
    return re.sub(r'[^a-zA-Z]', '', name).lower()

def collect_draftkings_data(schedule_input: str) -> Optional[Dict[str, Any]]:
    """Collect DraftKings data for NFL contests."""
    try:
        # Get draft group ID
        response = requests.get(CONTESTS_URL)
        response.raise_for_status()
        contests = response.json().get('Contests', [])
        
        draft_group_id = next((c['dg'] for c in contests if schedule_input in c['n']), None)
        
        if not draft_group_id:
            logger.error(f"No draft group ID found for '{schedule_input}' schedule")
            return None
        
        logger.info(f"Using draft group ID: {draft_group_id} for '{schedule_input}' schedule")
        
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

    fieldnames = data[0].keys()
    
    try:
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
        logger.info(f"Successfully wrote data to {filename}")
    except IOError as e:
        logger.error(f"Error writing to CSV file: {e}")

if __name__ == "__main__":
    schedule_input = input("Enter the schedule to search for (e.g., 'Fri-Mon', 'Sunday Only'): ")
    
    data = collect_draftkings_data(schedule_input)
    if data:
        print(f"Successfully collected data for {len(data)} players")
        write_to_csv(data)
        print("Sample data:")
        for player in data[:5]:  # Print first 5 players as a sample
            print(player)
    else:
        print("Failed to collect DraftKings data")