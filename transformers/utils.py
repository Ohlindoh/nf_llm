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

POSITION_COLUMN_MAPPING = {
    'QB': [
        'Player', 'Team', 'G', 
        'Pass_YDS', 'Pass_TD', 'Pass_ATT',
        'Rush_YDS', 'Rush_TD', 'Rush_ATT',
        'FL', 'FPTS', 'FPTS/G', 'ROST'
    ],
    'RB': [
        'Player', 'Team', 'G',
        'Rush_YDS', 'Rush_TD', 'Rush_ATT',
        'Rec_YDS', 'Rec_TD', 'REC',
        'FL', 'FPTS', 'FPTS/G', 'ROST'
    ],
    'WR': [
        'Player', 'Team', 'G',
        'Rec_YDS', 'Rec_TD', 'REC',
        'Rush_YDS', 'Rush_TD', 'Rush_ATT',
        'FL', 'FPTS', 'FPTS/G', 'ROST'
    ],
    'TE': [
        'Player', 'Team', 'G',
        'Rec_YDS', 'Rec_TD', 'REC',
        'FL', 'FPTS', 'FPTS/G', 'ROST'
    ],
    'DST': [
        'Player', 'Team', 'G',
        'SACK', 'INT', 'FR', 'FF', 'DEF_TD', 'SAFE',
        'PA', 'PA/G', 'YDS_AG', 'YDS_AG/G',
        'FPTS', 'FPTS/G', 'ROST'
    ]
}