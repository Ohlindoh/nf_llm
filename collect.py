import logging
from typing import Dict
import pandas as pd
import os
import sys
import argparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the collectors directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
collectors_dir = os.path.join(current_dir, 'collectors')
sys.path.append(collectors_dir)

# Import data collection functions
from fantasy_pros_projections import collect_and_clean_fantasy_pros_data
from dk import collect_draftkings_data
from collectors.fantasy_pros_stats import collect_fantasy_pros_stats
from collectors.utils import clean_player_name


OUTPUT_DIR = 'data'
OUTPUT_FILE = 'merged_fantasy_football_data.csv'

def collect_all_data(dk_contest_type: str) -> Dict[str, pd.DataFrame]:
    """
    Collect data from all available sources.
    Returns a dictionary with data source names as keys and DataFrames as values.
    """
    data_sources = {
        "fantasy_pros": collect_and_clean_fantasy_pros_data,
        "draftkings": lambda: collect_draftkings_data(dk_contest_type),
        "player_stats": collect_fantasy_pros_stats
    }

    collected_data = {}
    for source_name, collect_func in data_sources.items():
        logger.info(f"Collecting data from {source_name}")
        try:
            df = collect_func()
            if isinstance(df, pd.DataFrame) and not df.empty:
                # Clean player names
                if 'player_name' in df.columns:
                    df['player_name'] = df['player_name'].apply(clean_player_name)
                collected_data[source_name] = df
                logger.info(f"Successfully collected data from {source_name}")
            elif isinstance(df, list) and df:  # For DraftKings data which returns a list
                df = pd.DataFrame(df)
                if 'player_name' in df.columns:
                    df['player_name'] = df['player_name'].apply(clean_player_name)
                collected_data[source_name] = df
                logger.info(f"Successfully collected data from {source_name}")
            else:
                logger.warning(f"No data collected from {source_name}")
        except Exception as e:
            logger.error(f"Error collecting data from {source_name}: {str(e)}")

    return collected_data

def merge_dataframes(dataframes: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merge all collected dataframes into a single dataframe, ensuring unique entries per player.
    """
    if not dataframes:
        logger.error("No data to merge")
        return pd.DataFrame()

    # Start with the first dataframe
    merged_df = list(dataframes.values())[0]

    for df in list(dataframes.values())[1:]:
        # Ensure 'player_name' is the index for both dataframes
        merged_df.set_index('player_name', inplace=True)
        df.set_index('player_name', inplace=True)

        # Merge the dataframes
        merged_df = merged_df.combine_first(df)

        # Reset the index
        merged_df.reset_index(inplace=True)

    # Clean up column names
    merged_df.columns = merged_df.columns.str.replace('_x', '').str.replace('_y', '')

    # Remove any remaining duplicate rows
    merged_df.drop_duplicates(subset='player_name', keep='first', inplace=True)

    logger.info(f"Merged data shape: {merged_df.shape}")
    logger.info(f"Merged data columns: {merged_df.columns.tolist()}")
    return merged_df

def save_data(data: pd.DataFrame, filename: str) -> None:
    """
    Save the merged data to a CSV file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)
    data.to_csv(output_path, index=False)
    logger.info(f"Data saved to {output_path}")

def main(dk_contest_type: str) -> None:
    # Collect data from all sources
    collected_data = collect_all_data(dk_contest_type)

    # Merge all dataframes
    merged_data = merge_dataframes(collected_data)

    if not merged_data.empty:
        # Save merged data
        save_data(merged_data, OUTPUT_FILE)
        logger.info(f"Data collection completed. Total players: {len(merged_data)}")
    else:
        logger.error("Failed to produce merged data. Check individual source logs for details.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect fantasy football data including DraftKings contests.")
    parser.add_argument("dk_contest_type", type=str, help="DraftKings contest type (e.g., 'Early', 'Afternoon', 'Primetime', 'Main', 'Thursday', 'Sunday')")
    args = parser.parse_args()

    main(args.dk_contest_type)