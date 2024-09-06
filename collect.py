"""
This script orchestrates the collection and merging of fantasy football data from various sources.
It fetches projections, DraftKings data, and player statistics, then combines them into a single dataset.
"""

import os
import logging
from typing import Callable, Any, Union
import re
import numpy as np

import pandas as pd

from collectors import fantasy_pros_projections, dk, fantasy_pros_stats
from transformers import fantasy_pros_cleaner, dk_cleaner, utils

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'data'
OUTPUT_FILE = 'merged_fantasy_football_data.csv'

def collect_and_transform_data(collect_func: Callable[..., Any], 
                               transform_func: Callable[[Any], Union[pd.DataFrame, dict]], 
                               source_name: str) -> pd.DataFrame:
    logger.info(f"Processing data from {source_name}")
    try:
        raw_data = collect_func()
        logger.info(f"Raw data from {source_name}: {type(raw_data)}")
        if isinstance(raw_data, pd.DataFrame):
            logger.info(f"Raw data shape: {raw_data.shape}")
            logger.info(f"Raw data columns: {raw_data.columns.tolist()}")
        
        transformed_data = transform_func(raw_data)
        logger.info(f"Transformed data from {source_name}: {type(transformed_data)}")
        
        if isinstance(transformed_data, dict):
            transformed_data = pd.DataFrame(transformed_data)
        
        if isinstance(transformed_data, pd.DataFrame):
            logger.info(f"Transformed data shape: {transformed_data.shape}")
            logger.info(f"Transformed data columns: {transformed_data.columns.tolist()}")
            if 'player_name' not in transformed_data.columns:
                logger.warning(f"{source_name} data doesn't have a 'player_name' column. Skipping.")
                return pd.DataFrame()
        else:
            logger.warning(f"Unexpected data type from {source_name}. Expected DataFrame or dict, got {type(transformed_data)}")
            return pd.DataFrame()
        
        logger.info(f"Processed {len(transformed_data)} entries from {source_name}")
        return transformed_data
    except Exception as e:
        logger.error(f"Error processing {source_name} data: {str(e)}")
        return pd.DataFrame()

def clean_player_name(name: str) -> str:
    """Clean player name for consistent matching."""
    return re.sub(r'[^a-zA-Z]', '', name).lower()

def merge_dataframes(dataframes: list[pd.DataFrame]) -> pd.DataFrame:
    if not dataframes:
        return pd.DataFrame()
    
    # Assume the first dataframe is the base (Fantasy Pros projections)
    merged_df = dataframes[0]
    
    # Merge with other dataframes
    for df in dataframes[1:]:
        # Ensure 'player_name' is cleaned in the dataframe to be merged
        if 'player_name' in df.columns:
            df['player_name'] = df['player_name'].apply(clean_player_name)
        # Use inner join to keep only records that exist in both dataframes
        merged_df = pd.merge(merged_df, df, on='player_name', how='inner')
    
    # Remove any remaining rows with null values
    merged_df = merged_df.dropna()
    
    logger.info(f"Merged data shape: {merged_df.shape}")
    logger.info(f"Merged data columns: {merged_df.columns.tolist()}")
    return merged_df

def save_data(data: pd.DataFrame, filename: str) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)
    data.to_csv(output_path, index=False)
    logger.info(f"Data saved to {output_path}")

def main() -> None:
    try:
        current_week = utils.get_current_nfl_week()
        logger.info(f"Processing data for NFL Week: {current_week}")

        # Process Fantasy Pros Projections
        fantasy_pros_raw = fantasy_pros_projections.collect_fantasy_pros_data()
        logger.info(f"Raw Fantasy Pros data columns: {fantasy_pros_raw.columns.tolist()}")
        
        fantasy_pros_transformed = fantasy_pros_cleaner.transform_fantasy_pros_data(fantasy_pros_raw)
        logger.info(f"Transformed Fantasy Pros data columns: {fantasy_pros_transformed.columns.tolist()}")
        
        if 'player_name' not in fantasy_pros_transformed.columns:
            logger.error("'player_name' column not found in transformed Fantasy Pros data")
            return

        # Clean player names in Fantasy Pros data
        fantasy_pros_transformed['player_name'] = fantasy_pros_transformed['player_name'].apply(clean_player_name)
        
        logger.info(f"Fantasy Pros transformed data shape: {fantasy_pros_transformed.shape}")
        logger.info(f"Fantasy Pros transformed data columns: {fantasy_pros_transformed.columns.tolist()}")

        # Process DraftKings data
        dk_raw = dk.collect_draftkings_data()
        dk_transformed = dk_cleaner.process_draftkings_data(dk_raw)
        # Clean player names in DraftKings data
        dk_transformed['player_name'] = dk_transformed['player_name'].apply(clean_player_name)
        logger.info(f"DraftKings transformed data shape: {dk_transformed.shape}")
        logger.info(f"DraftKings transformed data columns: {dk_transformed.columns.tolist()}")

        # Merge dataframes
        merged_data = merge_dataframes([fantasy_pros_transformed, dk_transformed])

        if not merged_data.empty:
            save_data(merged_data, OUTPUT_FILE)
            logger.info(f"Data collection completed. Total players: {len(merged_data)}")
            logger.info(f"Columns in merged data: {merged_data.columns.tolist()}")
        else:
            logger.error("Failed to produce merged data. Check individual source logs for details.")

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()