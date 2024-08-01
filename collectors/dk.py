# collectors/draftkings.py

import requests
import logging
from pprint import pformat

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_draft_group_id():
    url = "https://www.draftkings.com/lobby/getcontests?sport=NFL"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if not data.get('Contests'):
            logging.error("No contests found in the API response")
            return None

        for contest in data['Contests']:
            if contest.get('n') == 'Classic':
                return contest.get('dg')

        # If no Classic contest is found, return the first contest's draft group ID
        first_contest = data['Contests'][0]
        logging.warning(f"No Classic NFL contest found. Using the first available contest: {first_contest.get('n')}")
        return first_contest.get('dg')

    except requests.RequestException as e:
        logging.error(f"Error fetching contest data: {e}")
    except ValueError as e:
        logging.error(f"Error parsing contest data: {e}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    
    return None

def fetch_draftkings_data(draft_group_id):
    url = f"https://api.draftkings.com/draftgroups/v1/draftgroups/{draft_group_id}/draftables"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error fetching data from DraftKings: {e}")
        return None

def collect_draftkings_data():
    draft_group_id = get_draft_group_id()
    if not draft_group_id:
        logging.error("Failed to get draft group ID")
        return None
    
    logging.info(f"Using draft group ID: {draft_group_id}")
    data = fetch_draftkings_data(draft_group_id)
    
    if data:
        logging.info("Successfully fetched DraftKings data")
        logging.debug(f"First few draftables: {pformat(data['draftables'][:2])}")
        return data
    else:
        logging.error("Failed to fetch DraftKings data")
        return None