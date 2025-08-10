import logging
import os
import sys
import argparse
from typing import Dict, Optional

import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add the collectors directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
collectors_dir = os.path.join(current_dir, "collectors")
sys.path.append(collectors_dir)

# Import data collection functions
from nf_llm.collectors.fantasy_pros_projections import (
    collect_and_clean_fantasy_pros_data,
)
from nf_llm.collectors.dk import collect_draftkings_data
from nf_llm.collectors.fantasy_pros_stats import collect_fantasy_pros_stats
from nf_llm.collectors.utils import clean_player_name, clean_dst_name


OUTPUT_DIR = "data"
OUTPUT_FILE = "merged_fantasy_football_data.csv"


def _normalise_df(raw: object) -> Optional[pd.DataFrame]:
    """Convert raw collector output into a cleaned ``DataFrame``.

    Several collectors return data in slightly different shapes (a DataFrame,
    a list of dictionaries, etc.).  This helper centralises the logic for
    coercing the output into a consistent format and applying common cleaning
    steps such as normalising player names.  It returns ``None`` when no data
    is available so callers can handle that scenario uniformly.
    """

    if isinstance(raw, list):
        raw = pd.DataFrame(raw)
    if isinstance(raw, pd.DataFrame) and not raw.empty:
        if "player_name" in raw.columns:
            # Determine the column that contains position information so DST
            # names can be normalised correctly.
            position_col = next(
                (
                    c
                    for c in raw.columns
                    if c.lower() in {"player_position_id", "position"}
                ),
                None,
            )
            if position_col:
                raw["player_name"] = raw.apply(
                    lambda row: (
                        clean_dst_name(row["player_name"])
                        if str(row[position_col]).upper() == "DST"
                        else clean_player_name(row["player_name"])
                    ),
                    axis=1,
                )
            else:
                raw["player_name"] = raw["player_name"].apply(clean_player_name)
        return raw
    return None


def collect_all_data(
    dk_contest_type: str, dk_draft_group_id: Optional[int] = None
) -> Dict[str, pd.DataFrame]:
    """Collect data from all available sources."""

    data_sources = {
        "fantasy_pros": collect_and_clean_fantasy_pros_data,
        "draftkings": lambda: collect_draftkings_data(
            dk_contest_type, dk_draft_group_id
        ),
        "player_stats": collect_fantasy_pros_stats,
    }

    collected_data: Dict[str, pd.DataFrame] = {}
    for source_name, collect_func in data_sources.items():
        logger.info(f"Collecting data from {source_name}")
        try:
            df = _normalise_df(collect_func())
            if df is not None:
                collected_data[source_name] = df
                logger.info(f"Successfully collected data from {source_name}")
            else:
                logger.warning(f"No data collected from {source_name}")
        except Exception as e:
            logger.error(f"Error collecting data from {source_name}: {e}")

    return collected_data


def merge_dataframes(dataframes: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merge all collected dataframes into a single dataframe, ensuring unique entries per player.
    Drop any rows with null values.
    """
    if not dataframes:
        logger.error("No data to merge")
        return pd.DataFrame()

    # Start with the first dataframe
    merged_df = list(dataframes.values())[0]

    for df in list(dataframes.values())[1:]:
        # Ensure 'player_name' is the index for both dataframes
        merged_df.set_index("player_name", inplace=True)
        df.set_index("player_name", inplace=True)

        # Merge the dataframes
        merged_df = merged_df.combine_first(df)

        # Reset the index
        merged_df.reset_index(inplace=True)

    # Clean up column names
    merged_df.columns = merged_df.columns.str.replace("_x", "").str.replace("_y", "")

    # Remove any remaining duplicate rows
    merged_df.drop_duplicates(subset="player_name", keep="first", inplace=True)

    # Drop rows with any null values
    merged_df.dropna(inplace=True)

    logger.info(f"Merged data shape before dropping nulls: {merged_df.shape}")
    logger.info(f"Merged data shape after dropping nulls: {merged_df.shape}")
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


def main(dk_contest_type: str, dk_draft_group_id: Optional[int] = None) -> None:
    # Collect data from all sources
    collected_data = collect_all_data(dk_contest_type, dk_draft_group_id)

    # Merge all dataframes
    merged_data = merge_dataframes(collected_data)

    if not merged_data.empty:
        # Save merged data
        save_data(merged_data, OUTPUT_FILE)
        logger.info(f"Data collection completed. Total players: {len(merged_data)}")
    else:
        logger.error(
            "Failed to produce merged data. Check individual source logs for details."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect fantasy football data including DraftKings contests."
    )
    parser.add_argument(
        "--dk_contest_type",
        type=str,
        default="Main",
        help="DraftKings contest type (e.g., 'Early', 'Afternoon', 'Primetime', 'Main', 'Thursday', 'Sunday')",
    )
    parser.add_argument(
        "--draft_group_id",
        type=int,
        default=None,
        help="DraftKings draft group ID (overrides contest type if provided)",
    )
    args = parser.parse_args()

    main(args.dk_contest_type, args.draft_group_id)
