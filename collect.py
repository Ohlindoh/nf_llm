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
        transformed_data = transform_func(raw_data)
        if isinstance(transformed_data, dict):
            transformed_data = pd.DataFrame(transformed_data)
        logger.info(f"Processed {len(transformed_data)} entries from {source_name}")
        return transformed_data
    except Exception as e:
        logger.error(f"Error processing {source_name} data: {str(e)}")
        return pd.DataFrame()

def clean_player_name(name: str) -> str:
    """Clean player name for consistent matching."""
    return re.sub(r'[^a-zA-Z]', '', name).lower()

def merge_dataframes(dataframes: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty_dfs = [df for df in dataframes if not df.empty]
    if not non_empty_dfs:
        return pd.DataFrame()
    
    # Assume the first dataframe is the base (likely the Fantasy Pros projections)
    merged_df = non_empty_dfs[0]
    
    # Clean player names in the base dataframe
    merged_df['clean_name'] = merged_df['player_name'].apply(clean_player_name)
    
    # Merge with other dataframes (DraftKings data and position-specific stats)
    for df in non_empty_dfs[1:]:
        df['clean_name'] = df['player_name'].apply(clean_player_name)
        merged_df = pd.merge(merged_df, df, on='clean_name', how='outer', suffixes=('', '_y'))
        
        # Combine columns with the same information
        for col in merged_df.columns:
            if col.endswith('_y'):
                base_col = col[:-2]
                merged_df[base_col] = merged_df[base_col].combine_first(merged_df[col])
                merged_df = merged_df.drop(col, axis=1)
    
    # Remove rows where all values are NaN
    merged_df = merged_df.dropna(how='all')
    
    # Fill NaN values in numeric columns with 0
    numeric_columns = merged_df.select_dtypes(include=[np.number]).columns
    merged_df[numeric_columns] = merged_df[numeric_columns].fillna(0)
    
    # Ensure each player only has one row
    merged_df = merged_df.groupby('clean_name', as_index=False).first()
    
    # Remove the clean_name column
    merged_df = merged_df.drop('clean_name', axis=1)
    
    logger.info(f"Merged data shape: {merged_df.shape}")
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

        data_sources = [
            (fantasy_pros_projections.collect_fantasy_pros_data, fantasy_pros_cleaner.transform_fantasy_pros_data, "Fantasy Pros Projections"),
            (dk.collect_draftkings_data, dk_cleaner.process_draftkings_data, "DraftKings"),
            (lambda: fantasy_pros_stats.collect_player_stats(current_week), lambda x: x, "Player Stats")
        ]

        processed_data = [collect_and_transform_data(*source) for source in data_sources]
        merged_data = merge_dataframes(processed_data)

        if not merged_data.empty:
            save_data(merged_data, OUTPUT_FILE)
            logger.info(f"Data collection completed. Total players: {len(merged_data)}")
        else:
            logger.error("Failed to produce merged data. Check individual source logs for details.")

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()