import requests
import logging
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONTESTS_URL = "https://www.draftkings.com/lobby/getcontests?sport=NFL"
DRAFTABLES_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/{}/draftables"

def collect_draftkings_data() -> Optional[Dict[str, Any]]:
    """Collect DraftKings data for NFL contests."""
    try:
        # Get draft group ID
        response = requests.get(CONTESTS_URL)
        response.raise_for_status()
        contests = response.json().get('Contests', [])
        
        draft_group_id = next((c['dg'] for c in contests if c['n'] == 'Classic'), contests[0]['dg'] if contests else None)
        
        if not draft_group_id:
            logger.error("No draft group ID found")
            return None
        
        logger.info(f"Using draft group ID: {draft_group_id}")
        
        # Fetch draftables data
        response = requests.get(DRAFTABLES_URL.format(draft_group_id))
        response.raise_for_status()
        data = response.json()
        
        logger.info(f"Successfully fetched data for {len(data['draftables'])} players")
        return data

    except requests.RequestException as e:
        logger.error(f"Error fetching data from DraftKings: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    
    return None

if __name__ == "__main__":
    data = collect_draftkings_data()
    if data:
        print(f"Successfully collected data for {len(data['draftables'])} players")
    else:
        print("Failed to collect DraftKings data")