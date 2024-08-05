# utils.py

import requests
import logging

logger = logging.getLogger(__name__)

ESPN_API_URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'

def get_current_nfl_week():
    """Fetch the current NFL week number from ESPN API."""
    response = requests.get(ESPN_API_URL)
    if response.status_code == 200:
        data = response.json()
        return data.get('week', {}).get('number')
    logger.error(f"Failed to retrieve data: {response.status_code}")
    return None