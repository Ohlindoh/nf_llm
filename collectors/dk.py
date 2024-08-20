# collectors/dk.py

import requests
import logging
from typing import Optional, Dict, Any
from pprint import pformat

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONTESTS_URL = "https://www.draftkings.com/lobby/getcontests?sport=NFL"
DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{}/draftables"

def get_draft_group_id() -> Optional[int]:
    """
    Fetch the draft group ID for the NFL Classic contest.
    
    Returns:
        Optional[int]: The draft group ID if found, None otherwise.
    """
    try:
        response = requests.get(CONTESTS_URL)
        response.raise_for_status()
        data = response.json()

        if not data.get('Contests'):
            logger.error("No contests found in the API response")
            return None

        for contest in data['Contests']:
            if contest.get('n') == 'Classic':
                return contest.get('dg')

        # If no Classic contest is found, return the first contest's draft group ID
        first_contest = data['Contests'][0]
        logger.warning(f"No Classic NFL contest found. Using the first available contest: {first_contest.get('n')}")
        return first_contest.get('dg')

    except requests.RequestException as e:
        logger.error(f"Error fetching contest data: {e}")
    except ValueError as e:
        logger.error(f"Error parsing contest data: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    
    return None

def fetch_draftkings_data(draft_group_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch draftable players data for a given draft group ID.
    
    Args:
        draft_group_id (int): The draft group ID to fetch data for.
    
    Returns:
        Optional[Dict[str, Any]]: The fetched data if successful, None otherwise.
    """
    url = DRAFTABLES_URL.format(draft_group_id)
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching data from DraftKings: {e}")
        return None

def collect_draftkings_data() -> Optional[Dict[str, Any]]:
    """
    Collect DraftKings data for NFL contests.
    
    Returns:
        Optional[Dict[str, Any]]: The collected DraftKings data if successful, None otherwise.
    """
    draft_group_id = get_draft_group_id()
    if not draft_group_id:
        logger.error("Failed to get draft group ID")
        return None
    
    logger.info(f"Using draft group ID: {draft_group_id}")
    data = fetch_draftkings_data(draft_group_id)
    
    if data:
        logger.info("Successfully fetched DraftKings data")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"First few draftables: {pformat(data['draftables'][:2])}")
        return data
    else:
        logger.error("Failed to fetch DraftKings data")
        return None

if __name__ == "__main__":
    data = collect_draftkings_data()
    if data:
        print(f"Successfully collected data for {len(data['draftables'])} players")
    else:
        print("Failed to collect DraftKings data")