import sys
from pathlib import Path
from datetime import datetime
import requests
import pandas as pd
import bs4
import logging
from typing import Optional, List, Dict

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from transformers.utils import get_current_nfl_week, POSITION_COLUMN_MAPPING

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_data(url: str) -> Optional[str]:
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching data from {url}: {e}")
        return None

def parse_table(html_content: str) -> Optional[pd.DataFrame]:
    soup = bs4.BeautifulSoup(html_content, "html.parser")
    table = soup.find('table', {'id': 'data'})
    
    if not table:
        logger.warning("No table found in the HTML content")
        return None

    headers = [header.text.strip() for header in table.find_all('th')]
    rows = table.find_all('tr')
    player_stats = [
        [col.text.strip() for col in row.find_all('td')]
        for row in rows[1:] if isinstance(row, bs4.element.Tag)
    ]

    return pd.DataFrame(player_stats, columns=headers)

def get_position_data(position: str, week: int) -> Optional[pd.DataFrame]:
    url = f'https://www.fantasypros.com/nfl/stats/{position.lower()}.php?range=week&week={week}'
    html_content = fetch_data(url)
    if html_content:
        df = parse_table(html_content)
        if df is not None:
            df['Position'] = position
            return df
    return None

def rename_columns(df: pd.DataFrame, position: str) -> pd.DataFrame:
    new_columns = []
    for i, col in enumerate(df.columns):
        if col in ['Player', 'Team', 'Position']:
            new_columns.append(col)
        else:
            new_columns.append(f"{position}_{col}_{i}")
    df.columns = new_columns
    return df

def collect_player_stats(week: int) -> Optional[pd.DataFrame]:
    positions = ['QB', 'RB', 'WR', 'TE', 'DST']
    all_data = []

    for position in positions:
        position_data = get_position_data(position, week)
        if position_data is not None:
            position_data = rename_columns(position_data, position)
            all_data.append(position_data)
            logger.info(f"{position} data processed successfully")
            logger.info(f"Columns for {position}: {position_data.columns.tolist()}")
        else:
            logger.error(f"Failed to process {position} data")

    if not all_data:
        logger.error("No data collected")
        return None

    return pd.concat(all_data, ignore_index=True)

def save_to_csv(data: pd.DataFrame, week: int):
    data_dir = project_root / 'data'
    data_dir.mkdir(exist_ok=True)
    current_date = datetime.now().strftime("%Y%m%d")
    filename = f"fantasy_pros_stats_week_{week}_{current_date}.csv"
    filepath = data_dir / filename
    data.to_csv(filepath, index=False)
    logger.info(f"Data saved to {filepath}")

def main():
    current_week = get_current_nfl_week()
    if current_week is None:
        logger.error("Failed to get current NFL week")
        return

    logger.info(f"Current NFL Week: {current_week}")
    stats = collect_player_stats(current_week)
    
    if stats is None:
        logger.error("Failed to collect player stats")
        return

    logger.info(f"Total rows: {len(stats)}")
    logger.info(f"All columns: {stats.columns.tolist()}")

    for position in ['QB', 'RB', 'WR', 'TE', 'DST']:
        position_data = stats[stats['Position'] == position]
        logger.info(f"\n{position} Columns: {', '.join(position_data.columns)}")
        logger.info(f"\nSample data for {position}:\n{position_data.head().to_string()}")

    save_to_csv(stats, current_week)

if __name__ == "__main__":
    main()