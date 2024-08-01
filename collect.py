# main.py

from collectors.fantasy_pros import collect_fantasy_pros_data
from collectors.dk import collect_draftkings_data
from transformers.fantasy_pros_cleaner import transform_fantasy_pros_data
from transformers.dk_cleaner import process_draftkings_data
import pandas as pd
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

def merge_data(fantasy_pros_data, draftkings_data):
    logger.info("Merging Fantasy Pros and DraftKings data")
    merged_data = pd.merge(fantasy_pros_data, draftkings_data, how='left', on='player_name')
    logger.info(f"Merged data shape: {merged_data.shape}")
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
        if fantasy_pros_data is None:
            logger.warning("Proceeding without Fantasy Pros data")
            fantasy_pros_data = pd.DataFrame()

        draftkings_data = collect_and_transform_draftkings()
        if draftkings_data is None:
            logger.warning("Proceeding without DraftKings data")
            draftkings_data = pd.DataFrame()

        if fantasy_pros_data.empty and draftkings_data.empty:
            logger.error("No data collected from either source. Exiting.")
            return

        merged_data = merge_data(fantasy_pros_data, draftkings_data)
        save_data(merged_data, "merged_fantasy_football_data.csv")

        logger.info("Data collection and processing completed")
        logger.info(f"Total players in merged data: {len(merged_data)}")
        logger.info("\nFirst few rows of merged data:")
        logger.info(merged_data.head().to_string())

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()