import requests
import pandas as pd
import re
import json
import logging
from typing import Optional, Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = 'https://www.fantasypros.com/nfl/rankings'
RANKINGS = ['qb.php', 'ppr-rb.php', 'ppr-wr.php', 'ppr-te.php', 'dst.php']

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

def collect_fantasy_pros_data() -> pd.DataFrame:
    """Collect and combine data from all ranking pages."""
    all_data: List[Dict] = []

    for ranking in RANKINGS:
        url = f'{BASE_URL}/{ranking}'
        logger.info(f"Fetching data from {url}")
        
        html_content = fetch_fantasy_pros_data(url)
        if not html_content:
            continue

        data = parse_fantasy_pros_data(html_content)
        if data and 'players' in data:
            all_data.extend(data['players'])
            logger.info(f"Successfully collected data for {ranking}")
        else:
            logger.warning(f"No valid data found for {url}")

    if not all_data:
        logger.error("No data collected")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    logger.info(f"Total players collected: {len(df)}")
    return df

if __name__ == "__main__":
    df = collect_fantasy_pros_data()
    if not df.empty:
        print(df.head())
        print(f"Total players collected: {len(df)}")
        print(f"Columns: {df.columns.tolist()}")
    else:
        print("No data collected.")