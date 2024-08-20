import sys
from pathlib import Path
from datetime import datetime
import requests
import pandas as pd
import bs4
import logging
from typing import Optional, Dict
from io import StringIO

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from transformers.utils import get_current_nfl_week

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

POSITIONS = ['QB', 'RB', 'WR', 'TE', 'DST']
BASE_URL = 'https://www.fantasypros.com/nfl/stats/{}.php?range=week&week={}'

def fetch_data(url: str) -> Optional[str]:
    """
    Fetch HTML content from a given URL.

    Args:
        url (str): The URL to fetch data from.

    Returns:
        Optional[str]: The HTML content if successful, None otherwise.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching data from {url}: {e}")
        return None

def parse_table(html_content: str) -> Optional[pd.DataFrame]:
    """
    Parse the HTML content to extract the data table.

    Args:
        html_content (str): The HTML content to parse.

    Returns:
        Optional[pd.DataFrame]: The parsed data as a DataFrame if successful, None otherwise.
    """
    soup = bs4.BeautifulSoup(html_content, "html.parser")
    table = soup.find('table', {'id': 'data'})
    
    if not table:
        logger.warning("No table found in the HTML content")
        return None

    df = pd.read_html(StringIO(str(table)))[0]
    df.columns = df.columns.map(lambda x: x[1] if isinstance(x, tuple) else x)
    return df

def get_position_data(position: str, week: int) -> Optional[pd.DataFrame]:
    """
    Fetch and process data for a specific position and week.

    Args:
        position (str): The player position (e.g., 'QB', 'RB').
        week (int): The NFL week number.

    Returns:
        Optional[pd.DataFrame]: Processed data for the position if successful, None otherwise.
    """
    url = BASE_URL.format(position.lower(), week)
    html_content = fetch_data(url)
    if html_content:
        df = parse_table(html_content)
        if df is not None:
            df['Position'] = position
            df = df.rename(columns={'Player': 'player_name'})
            return df
    return None

def rename_columns(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """
    Rename columns to include the position prefix.

    Args:
        df (pd.DataFrame): The DataFrame to process.
        position (str): The player position.

    Returns:
        pd.DataFrame: The DataFrame with renamed columns.
    """
    return df.rename(columns={col: f"{position}_{col}" for col in df.columns 
                              if col not in ['player_name', 'Team', 'Position']})

def collect_player_stats(week: int) -> Dict[str, pd.DataFrame]:
    """
    Collect player stats for all positions for a given week, keeping each position separate.

    Args:
        week (int): The NFL week number.

    Returns:
        Dict[str, pd.DataFrame]: A dictionary with positions as keys and their respective DataFrames as values.
    """
    position_data = {}

    for position in POSITIONS:
        df = get_position_data(position, week)
        if df is not None:
            df = rename_columns(df, position)
            df['Position'] = position
            df['player_name'] = df['player_name'].str.lower().str.replace(' ', '')
            df.reset_index(drop=True, inplace=True)
            position_data[position] = df
            logger.info(f"{position} data processed successfully. Shape: {df.shape}")
            logger.info(f"Columns for {position}: {df.columns.tolist()}")
            logger.info(f"Sample data for {position}:\n{df.head().to_string()}")
        else:
            logger.error(f"Failed to process {position} data")

    return position_data

def save_to_csv(data: pd.DataFrame, week: int, suffix: str = ""):
    """
    Save the collected data to a CSV file.

    Args:
        data (pd.DataFrame): The data to save.
        week (int): The NFL week number.
        suffix (str): Optional suffix for the filename.
    """
    data_dir = project_root / 'data'
    data_dir.mkdir(exist_ok=True)
    current_date = datetime.now().strftime("%Y%m%d")
    filename = f"fantasy_pros_stats_week_{week}_{current_date}{('_' + suffix) if suffix else ''}.csv"
    filepath = data_dir / filename
    data.to_csv(filepath, index=False)
    logger.info(f"Data saved to {filepath}")

def main():
    """
    Main function to orchestrate the data collection, analysis, and saving process.
    """
    try:
        current_week = get_current_nfl_week()
        if current_week is None:
            logger.error("Failed to get current NFL week")
            return

        logger.info(f"Current NFL Week: {current_week}")
        position_stats = collect_player_stats(current_week)
        
        if not position_stats:
            logger.error("Failed to collect player stats for any position")
            return

        for position, df in position_stats.items():
            logger.info(f"\nAnalyzing {position} data:")
            logger.info(f"Shape: {df.shape}")
            logger.info(f"Columns: {df.columns.tolist()}")
            logger.info(f"Data types:\n{df.dtypes}")
            logger.info(f"Number of unique players: {df['player_name'].nunique()}")
            logger.info(f"Sample data:\n{df.head().to_string()}")

            # Save individual position data
            save_to_csv(df, current_week, f"{position}_stats")

        logger.info("Data processing and saving completed for all positions")

        # Here you can add logic to combine the data if it looks consistent across positions
        # For now, we're keeping them separate to analyze the structure

    except Exception as e:
        logger.exception(f"An unexpected error occurred in main: {str(e)}")

if __name__ == "__main__":
    main()