"""
This script orchestrates the collection and merging of fantasy football data from various sources.
It fetches projections, DraftKings data, and player statistics, then combines them into a single dataset.
"""

import os
import logging
from typing import Callable, Any, Optional

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

def collect_and_transform_data(collect_func: Callable[..., Any], 
                               transform_func: Callable[[Any], pd.DataFrame], 
                               source_name: str) -> Optional[pd.DataFrame]:
    """
    Collect and transform data from a specific source.

    Args:
        collect_func (Callable): Function to collect raw data.
        transform_func (Callable): Function to transform raw data into a DataFrame.
        source_name (str): Name of the data source for logging.

    Returns:
        Optional[pd.DataFrame]: Transformed data if successful, None otherwise.
    """
    logger.info(f"Processing data from {source_name}")
    try:
        raw_data = collect_func()
        if raw_data is None or (isinstance(raw_data, pd.DataFrame) and raw_data.empty):
            logger.error(f"No data collected from {source_name}")
            return None

        transformed_data = transform_func(raw_data)
        if transformed_data is None or transformed_data.empty:
            logger.error(f"{source_name} data transformation resulted in empty DataFrame")
            return None

        logger.info(f"Successfully processed {len(transformed_data)} entries from {source_name}")
        return transformed_data
    except Exception as e:
        logger.exception(f"Error processing {source_name} data: {str(e)}")
        return None

def merge_dataframes(dataframes: list[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    Merge multiple DataFrames on the 'player_name' column.

    Args:
        dataframes (list[pd.DataFrame]): List of DataFrames to merge.

    Returns:
        Optional[pd.DataFrame]: Merged DataFrame if successful, None otherwise.
    """
    if not dataframes:
        logger.error("No DataFrames to merge")
        return None

    merged_df = dataframes[0]
    for df in dataframes[1:]:
        merged_df = pd.merge(merged_df, df, on='player_name', how='outer')

    logger.info(f"Merged data shape: {merged_df.shape}")
    return merged_df

def save_data(data: pd.DataFrame, filename: str) -> None:
    """
    Save the DataFrame to a CSV file.

    Args:
        data (pd.DataFrame): Data to save.
        filename (str): Name of the output file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)
    data.to_csv(output_path, index=False)
    logger.info(f"Data saved to {output_path}")

def main() -> None:
    """
    Main function to orchestrate the data collection, merging, and saving process.
    """
    try:
        current_week = get_current_nfl_week()
        logger.info(f"Processing data for NFL Week: {current_week}")

        data_sources = [
            (collect_fantasy_pros_data, transform_fantasy_pros_data, "Fantasy Pros Projections"),
            (collect_draftkings_data, process_draftkings_data, "DraftKings"),
            (lambda: collect_player_stats(current_week), lambda x: x, "Player Stats")
        ]

        processed_data = [collect_and_transform_data(*source) for source in data_sources if source is not None]
        merged_data = merge_dataframes([df for df in processed_data if df is not None])

        if merged_data is not None and not merged_data.empty:
            save_data(merged_data, OUTPUT_FILE)
            logger.info(f"Data collection and processing completed successfully.")
            logger.info(f"Total players in merged data: {len(merged_data)}")
        else:
            logger.error("Failed to produce merged data. Check individual source logs for details.")

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()