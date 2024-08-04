# collect.py

from collectors.fantasy_pros_projections import collect_fantasy_pros_data
from collectors.dk import collect_draftkings_data
from collectors.fantasy_pros_stats import collect_player_stats
from transformers.fantasy_pros_cleaner import transform_fantasy_pros_data, transform_player_stats
from transformers.dk_cleaner import process_draftkings_data
import pandas as pd
import requests
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_current_nfl_week():
    # Define the ESPN scoreboard endpoint
    url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'

    # Make a GET request to the ESPN API
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()

        # Extract the current week number
        current_week = data.get('week', {}).get('number', None)
        return current_week
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        return None

# Get the current NFL week
current_week = get_current_nfl_week()
print(f"Current NFL Week: {current_week}")

def collect_and_transform_fantasy_pros():
    logger.info("Collecting data from Fantasy Pros")
    raw_data = collect_fantasy_pros_data()
    if raw_data is None or raw_data.empty:
        logger.error("Failed to collect data from Fantasy Pros")
        return None
    
    logger.info("Transforming Fantasy Pros data")
    transformed_data = transform_fantasy_pros_data(raw_data)
    if transformed_data.empty:
        logger.error("Fantasy Pros data transformation resulted in empty DataFrame")
        return None
    
    return transformed_data

def collect_and_transform_draftkings():
    logger.info("Collecting data from DraftKings")
    raw_data = collect_draftkings_data()
    if raw_data is None:
        logger.error("Failed to collect data from DraftKings")
        return None
    
    logger.info("Transforming DraftKings data")
    transformed_data = process_draftkings_data(raw_data)
    if transformed_data is None or transformed_data.empty:
        logger.error("DraftKings data transformation resulted in empty DataFrame")
        return None
    
    return transformed_data

def collect_and_transform_player_stats():
    logger.info("Collecting player stats from Fantasy Pros")
    raw_data = collect_player_stats()
    if raw_data is None or raw_data.empty:
        logger.error("Failed to collect player stats from Fantasy Pros")
        return None
    
    logger.info(f"Raw player stats data shape: {raw_data.shape}")
    logger.info(f"Raw player stats columns: {raw_data.columns.tolist()}")
    
    logger.info("Transforming player stats data")
    transformed_data = transform_player_stats(raw_data)
    if transformed_data.empty:
        logger.error("Player stats data transformation resulted in empty DataFrame")
        return None
    
    logger.info(f"Transformed player stats data shape: {transformed_data.shape}")
    logger.info(f"Transformed player stats columns: {transformed_data.columns.tolist()}")
    
    return transformed_data

def merge_data(fantasy_pros_data, draftkings_data, player_stats_data):
    logger.info("Merging Fantasy Pros, DraftKings, and player stats data")
    
    # Debug information
    logger.info(f"Fantasy Pros data columns: {fantasy_pros_data.columns.tolist()}")
    logger.info(f"DraftKings data columns: {draftkings_data.columns.tolist()}")
    logger.info(f"Player stats data columns: {player_stats_data.columns.tolist()}")
    
    # Merge Fantasy Pros and DraftKings data
    merged_data = pd.merge(fantasy_pros_data, draftkings_data, how='outer', on='player_name', suffixes=('_fp', '_dk'))
    logger.info(f"Merged data (FP + DK) shape: {merged_data.shape}")
    
    # Check if 'player_name' exists in player_stats_data
    if 'player_name' not in player_stats_data.columns:
        logger.warning("'player_name' column not found in player stats data. Skipping merge with player stats.")
        return merged_data
    
    # Check if 'player_team_id' exists in both merged_data and player_stats_data
    merge_columns = ['player_name']
    if 'player_team_id' in merged_data.columns and 'player_team_id' in player_stats_data.columns:
        merge_columns.append('player_team_id')
    
    # Merge with player stats data
    merged_data = pd.merge(merged_data, player_stats_data, how='outer', on=merge_columns, suffixes=('', '_ps'))
    logger.info(f"Final merged data shape: {merged_data.shape}")
    
    return merged_data

def save_data(data, filename):
    output_dir = 'data'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)
    data.to_csv(output_path, index=False)
    logger.info(f"Data saved to {output_path}")

def main():
    try:
        fantasy_pros_data = collect_and_transform_fantasy_pros()
        if fantasy_pros_data is None or fantasy_pros_data.empty:
            logger.warning("Proceeding without Fantasy Pros data")
            fantasy_pros_data = pd.DataFrame()

        draftkings_data = collect_and_transform_draftkings()
        if draftkings_data is None or draftkings_data.empty:
            logger.warning("Proceeding without DraftKings data")
            draftkings_data = pd.DataFrame()

        player_stats_data = collect_and_transform_player_stats()
        if player_stats_data is None or player_stats_data.empty:
            logger.warning("Proceeding without player stats data")
            player_stats_data = pd.DataFrame()

        if fantasy_pros_data.empty and draftkings_data.empty and player_stats_data.empty:
            logger.error("No data collected from any source. Exiting.")
            return

        # Debug information
        logger.info(f"Fantasy Pros data shape: {fantasy_pros_data.shape}")
        logger.info(f"DraftKings data shape: {draftkings_data.shape}")
        logger.info(f"Player stats data shape: {player_stats_data.shape}")

        merged_data = merge_data(fantasy_pros_data, draftkings_data, player_stats_data)
        
        if merged_data.empty:
            logger.error("Merged data is empty. Exiting.")
            return

        save_data(merged_data, "merged_fantasy_football_data.csv")

        logger.info("Data collection and processing completed")
        logger.info(f"Total players in merged data: {len(merged_data)}")
        logger.info("\nFirst few rows of merged data:")
        logger.info(merged_data.head().to_string())

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()