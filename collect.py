# collect.py

import os
import logging
import pandas as pd

from collectors.fantasy_pros_projections import collect_fantasy_pros_data
from collectors.dk import collect_draftkings_data
from collectors.fantasy_pros_stats import collect_player_stats
from transformers.fantasy_pros_cleaner import transform_fantasy_pros_data
from transformers.dk_cleaner import process_draftkings_data
from transformers.utils import get_current_nfl_week

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
OUTPUT_DIR = 'data'
OUTPUT_FILE = 'merged_fantasy_football_data.csv'

def collect_and_transform_data(collect_func, transform_func, source_name):
    """Generic function to collect and transform data from a source."""
    logger.info(f"Collecting data from {source_name}")
    raw_data = collect_func()
    
    if raw_data is None:
        logger.error(f"Failed to collect data from {source_name}")
        return pd.DataFrame()
    
    if isinstance(raw_data, dict) and not raw_data:
        logger.error(f"Collected empty dictionary from {source_name}")
        return pd.DataFrame()
    
    if isinstance(raw_data, pd.DataFrame) and raw_data.empty:
        logger.error(f"Collected empty DataFrame from {source_name}")
        return pd.DataFrame()
    
    logger.info(f"Transforming {source_name} data")
    transformed_data = transform_func(raw_data)
    
    if transformed_data is None or (isinstance(transformed_data, pd.DataFrame) and transformed_data.empty):
        logger.error(f"{source_name} data transformation resulted in empty DataFrame")
        return pd.DataFrame()
    
    return transformed_data

def merge_data(fantasy_pros_data, draftkings_data, player_stats_data):
    """Merge data from different sources."""
    logger.info("Merging Fantasy Pros, DraftKings, and player stats data")
    
    # Log data shapes
    for name, data in [("Fantasy Pros", fantasy_pros_data), 
                       ("DraftKings", draftkings_data), 
                       ("Player stats", player_stats_data)]:
        logger.info(f"{name} data shape: {data.shape}")
        logger.info(f"{name} columns: {data.columns.tolist()}")
    
    # Merge Fantasy Pros and DraftKings data
    merged_data = pd.merge(fantasy_pros_data, draftkings_data, 
                           how='outer', on='player_name', suffixes=('_fp', '_dk'))
    logger.info(f"Merged data (FP + DK) shape: {merged_data.shape}")
    
    # Merge with player stats data if possible
    if 'player_name' in player_stats_data.columns:
        merge_columns = ['player_name']
        if 'player_team_id' in merged_data.columns and 'player_team_id' in player_stats_data.columns:
            merge_columns.append('player_team_id')
        
        merged_data = pd.merge(merged_data, player_stats_data, 
                               how='outer', on=merge_columns, suffixes=('', '_ps'))
        logger.info(f"Final merged data shape: {merged_data.shape}")
    else:
        logger.warning("'player_name' column not found in player stats data. Skipping merge with player stats.")
    
    return merged_data

def save_data(data, filename):
    """Save the merged data to a CSV file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)
    data.to_csv(output_path, index=False)
    logger.info(f"Data saved to {output_path}")

def main():
    try:
        current_week = get_current_nfl_week()
        logger.info(f"Current NFL Week: {current_week}")

        # Collect and transform data from different sources
        fantasy_pros_data = collect_and_transform_data(
            collect_fantasy_pros_data, transform_fantasy_pros_data, "Fantasy Pros")
        draftkings_data = collect_and_transform_data(
            collect_draftkings_data, process_draftkings_data, "DraftKings")
        player_stats_data = collect_and_transform_data(
            lambda: collect_player_stats(current_week), lambda x: x, "Player Stats")

        # Check if any data was collected
        if all(data.empty for data in [fantasy_pros_data, draftkings_data, player_stats_data]):
            logger.error("No data collected from any source. Exiting.")
            return

        # Merge and save data
        merged_data = merge_data(fantasy_pros_data, draftkings_data, player_stats_data)
        if not merged_data.empty:
            save_data(merged_data, OUTPUT_FILE)
            logger.info(f"Total players in merged data: {len(merged_data)}")
            logger.info("\nFirst few rows of merged data:")
            logger.info(merged_data.head().to_string())
        else:
            logger.error("Merged data is empty. Exiting.")

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()