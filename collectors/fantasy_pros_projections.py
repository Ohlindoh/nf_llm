import requests
import pandas as pd
import re
import json
import logging
from typing import Optional, Dict, List
import os

from collectors.utils import clean_player_name, clean_dst_name

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = 'https://www.fantasypros.com/nfl/rankings'
RANKINGS = ['qb.php', 'ppr-rb.php', 'ppr-wr.php', 'ppr-te.php', 'dst.php']
OUTPUT_DIR = 'data'
OUTPUT_FILE = 'fantasy_projections.csv'

def fetch_fantasy_pros_data(url: str) -> Optional[str]:
    """Fetch data from the given URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching data from {url}: {e}")
        return None

def parse_fantasy_pros_data(html_content: str) -> Optional[Dict]:
    """Parse the HTML content to extract player data."""
    try:
        # Look for any JavaScript object that contains player data
        match = re.search(r'var\s+(?:ecrData|rankingsData)\s*=\s*({.*?});', html_content, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            if 'players' in data:
                return data
        logger.warning("No player data found in the HTML content")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON data: {e}")
        return None

def collect_and_clean_fantasy_pros_data() -> pd.DataFrame:
    """Collect, combine, and clean data from all ranking pages."""
    all_data: List[Dict] = []

    for ranking in RANKINGS:
        url = f'{BASE_URL}/{ranking}'
        logger.info(f"Fetching data from {url}")
        
        html_content = fetch_fantasy_pros_data(url)
        if not html_content:
            continue

        data = parse_fantasy_pros_data(html_content)
        if data and 'players' in data:
            # Add more detailed logging here
            logger.info(f"Data structure for {ranking}: {data.keys()}")
            logger.info(f"Player data structure: {data['players'][0].keys() if data['players'] else 'No players'}")
            all_data.extend(data['players'])
            logger.info(f"Successfully collected data for {ranking}")
        else:
            logger.warning(f"No valid data found for {url}")

    if not all_data:
        logger.error("No data collected")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    
    # Log the columns before selection
    logger.info(f"All columns before selection: {df.columns.tolist()}")
    
    # Select only the columns we want to keep
    columns_to_keep = [
        'player_name', 'player_team_id', 'player_position_id', 
        'rank_ecr', 'pos_rank', 'r2p_pts',
    ]
    df = df[columns_to_keep]
    
    # Rename 'r2p_pts' to 'projected_points'
    df = df.rename(columns={'r2p_pts': 'projected_points'})
    
    # Clean player names
    df['player_name'] = df.apply(lambda row: clean_dst_name(row['player_name']) if row['player_position_id'] == 'DST' else clean_player_name(row['player_name']), axis=1)
    
    # Add logging to check cleaned names
    for original, cleaned in zip(df['player_name'], df['player_name'].apply(clean_player_name)):
        logger.info(f"Cleaned name: {original} -> {cleaned}")
    
    logger.info(f"Total players collected and cleaned: {len(df)}")
    logger.info(f"Columns after cleaning: {df.columns.tolist()}")
    return df

def save_fantasy_pros_data(df: pd.DataFrame) -> None:
    """Save the collected and cleaned Fantasy Pros data to a CSV file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    df.to_csv(output_path, index=False)
    logger.info(f"Fantasy Pros data saved to {output_path}")

if __name__ == "__main__":
    df = collect_and_clean_fantasy_pros_data()
    if not df.empty:
        print(df.head())
        print(f"Total players collected and cleaned: {len(df)}")
        print(f"Columns: {df.columns.tolist()}")
        save_fantasy_pros_data(df)
    else:
        print("No data collected.")