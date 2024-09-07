import requests
import logging
import datetime
import re

logger = logging.getLogger(__name__)

ESPN_API_URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'
DRAFTKINGS_API_URL = 'https://www.draftkings.com/lobby/getcontests?sport=NFL'

TEAM_NAME_MAPPING = {
    'sanfrancisco49ers': '49ers', 'dallascowboys': 'cowboys', 'philadelphiaeagles': 'eagles',
    'buffalobills': 'bills', 'newyorkjets': 'jets', 'newenglandpatriots': 'patriots',
    'baltimoreravens': 'ravens', 'denverbroncos': 'broncos', 'pittsburghsteelers': 'steelers',
    'neworleanssaints': 'saints', 'kansascitychiefs': 'chiefs', 'miamidolphins': 'dolphins',
    'washingtoncommanders': 'commanders', 'cincinnatibengals': 'bengals', 'clevelandbrowns': 'browns',
    'greenbaypackers': 'packers', 'losangeleschargers': 'chargers', 'jacksonvillejaguars': 'jaguars',
    'tampabaybuccaneers': 'buccaneers', 'seattleseahawks': 'seahawks', 'indianapoliscolts': 'colts',
    'carolinapanthers': 'panthers', 'tennesseetitans': 'titans', 'newyorkgiants': 'giants',
    'detroitlions': 'lions', 'losangelesrams': 'rams', 'minnesotavikings': 'vikings',
    'atlantafalcons': 'falcons', 'arizonacardinals': 'cardinals', 'houstontexans': 'texans',
    'chicagobears': 'bears', 'lasvegasraiders': 'raiders'
}

def get_current_nfl_week():
    """Fetch the current NFL week number from ESPN API based on the current date."""
    response = requests.get(ESPN_API_URL)
    if response.status_code == 200:
        data = response.json()
        current_date = datetime.datetime.utcnow()
        season_info = data.get('season', {}).get('entries', [])
        for week in season_info:
            start = datetime.datetime.fromisoformat(week['startDate'].replace('Z', '+00:00'))
            end = datetime.datetime.fromisoformat(week['endDate'].replace('Z', '+00:00'))
            if start <= current_date <= end:
                return week['value']
        return '1'  # Default to week 1 if current date is not within any week range
    logger.error(f"Failed to retrieve data: {response.status_code}")
    return None

def get_draftkings_contest_names():
    """Fetch the contest names from DraftKings NFL contests where gameType is 'Classic'."""
    try:
        response = requests.get(DRAFTKINGS_API_URL)
        if response.status_code == 200:
            data = response.json()
            # Filter contests where "gameType" is "Classic"
            contest_names = [contest['n'] for contest in data.get('Contests', []) if contest.get('gameType') == 'Classic']
            logger.info(f"Successfully fetched {len(contest_names)} contest names with gameType 'Classic'.")
            return contest_names
        else:
            logger.error(f"Failed to fetch DraftKings contests: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error while fetching DraftKings contests: {e}")
        return []

def clean_player_name(name: str) -> str:
    """
    Clean player name for consistent matching across all modules.
    Remove suffixes, spaces, and non-alphabetic characters.
    """
    # Remove team name in parentheses
    name = re.sub(r'\([^)]*\)', '', name)
    # Remove suffixes (including 'II', 'III', 'IV', 'V', 'Jr', 'Sr', etc.)
    name = re.sub(r'\s+(?:I{1,3}|IV|V?I{0,3}|Jr\.?|Sr\.?)\.?\s*$', '', name)
    # Convert to lowercase, remove extra spaces and non-alphabetic characters
    return re.sub(r'[^a-z]', '', name.strip().lower())

def clean_dst_name(name: str) -> str:
    """
    Clean DST name for consistent matching across all modules.
    """
    cleaned_name = re.sub(r'[^a-z]', '', name.strip().lower())
    for full_name, short_name in TEAM_NAME_MAPPING.items():
        if full_name in cleaned_name:
            return f"{short_name.lower()}"
    return f"{cleaned_name}"

# Easy invocation example for testing
if __name__ == "__main__":
    # Example: Fetch and print current NFL week
    current_week = get_current_nfl_week()
    print(f"Current NFL Week: {current_week}")

    # Example: Fetch and print DraftKings contest names with gameType 'Classic'
    draftkings_contests = get_draftkings_contest_names()
    print(f"DraftKings Contests (Classic gameType): {draftkings_contests}")
# Easy invocation example for testing
if __name__ == "__main__":
    # Example: Fetch and print current NFL week
    current_week = get_current_nfl_week()
    print(f"Current NFL Week: {current_week}")

    # Example: Fetch and print DraftKings contest names
    draftkings_contests = get_draftkings_contest_names()
    print(f"DraftKings Contests: {draftkings_contests}")

# Existing mapping for player positions
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
