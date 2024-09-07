import sys
from pathlib import Path
import requests
import pandas as pd
from bs4 import BeautifulSoup
from typing import Optional, Dict
from io import StringIO
import re

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from transformers.utils import get_current_nfl_week
from transformers.utils import clean_player_name, get_current_nfl_week

POSITIONS = ['QB', 'RB', 'WR', 'TE', 'DST']
BASE_URL = 'https://www.fantasypros.com/nfl/stats/{}.php?range=week&week={}'

def get_column_mapping(position: str) -> Dict[str, str]:
    if position == 'QB':
        return {
            'ATT': 'QB_PASS_ATT',
            'YDS': 'QB_PASS_YDS',
            'TD': 'QB_PASS_TD',
            'ATT': 'QB_RUSH_ATT',
            'YDS': 'QB_RUSH_YDS',
            'TD': 'QB_RUSH_TD',
            'FPTS': 'QB_FPTS'
        }
    elif position == 'RB':
        return {
            'ATT': 'RB_RUSH_ATT',
            'YDS': 'RB_RUSH_YDS',
            'TD': 'RB_RUSH_TD',
            'REC': 'RB_REC',
            'YDS': 'RB_REC_YDS',
            'TD': 'RB_REC_TD',
            'FPTS': 'RB_FPTS'
        }
    elif position in ['WR', 'TE']:
        return {
            'REC': f'{position}_REC',
            'TGT': f'{position}_TGT',
            'YDS': f'{position}_REC_YDS',
            'TD': f'{position}_REC_TD',
            'FPTS': f'{position}_FPTS'
        }
    elif position == 'DST':
        return {
            'SACK': 'DST_SACK',
            'INT': 'DST_INT',
            'FR': 'DST_FR',
            'DEF TD': 'DST_TD',
            'PA': 'DST_PA',
            'FPTS': 'DST_FPTS'
        }
    return {}

def fetch_and_parse_data(position: str, week: int) -> Optional[pd.DataFrame]:
    url = BASE_URL.format(position.lower(), week)
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find('table', {'id': 'data'})
        if not table:
            return None
        df = pd.read_html(StringIO(str(table)))[0]
        df.columns = df.columns.map(lambda x: x[1] if isinstance(x, tuple) else x)
        
        # Rename columns based on position
        column_mapping = get_column_mapping(position)
        df = df.rename(columns=column_mapping)
        
        # Select only the mapped columns and 'Player'
        columns_to_keep = ['Player'] + list(column_mapping.values())
        df = df[columns_to_keep]
        
        df = df.rename(columns={'Player': 'player_name'})
        df['Position'] = position
        df['player_name'] = df['player_name'].apply(clean_player_name)
        return df
    except Exception as e:
        print(f"Error processing {position} data: {e}")
        return None

def clean_player_name(name: str) -> str:
    # Remove team name in parentheses
    name = re.sub(r'\([^)]*\)', '', name)
    # Remove suffixes and clean up
    name = re.sub(r"(?:I{1,3}|IV|V?I{0,3}|Jr|Sr)\s*$", "", name)
    # Convert to lowercase, remove extra spaces, and replace spaces with empty string
    return name.strip().lower().replace(' ', '')

def collect_player_stats(week: int) -> Dict[str, pd.DataFrame]:
    return {pos: fetch_and_parse_data(pos, week) for pos in POSITIONS if fetch_and_parse_data(pos, week) is not None}

def save_to_csv(data: pd.DataFrame, week: int, suffix: str = ""):
    data_dir = project_root / 'data'
    data_dir.mkdir(exist_ok=True)
    filename = f"fantasy_pros_stats_week_{week}_{suffix}.csv"
    data.to_csv(data_dir / filename, index=False)

def collect_fantasy_pros_stats() -> pd.DataFrame:
    current_week = get_current_nfl_week()
    if current_week is None:
        print("Failed to get current NFL week")
        return pd.DataFrame()

    position_stats = collect_player_stats(current_week)
    
    if not position_stats:
        print("Failed to collect player stats for any position")
        return pd.DataFrame()

    # Combine all position dataframes into one
    combined_df = pd.concat(position_stats.values(), ignore_index=True)

    # Save the combined data
    save_to_csv(combined_df, current_week, "all_positions")

    return combined_df

def main():
    current_week = get_current_nfl_week()
    if current_week is None:
        print("Failed to get current NFL week")
        return

    position_stats = collect_player_stats(current_week)
    
    if not position_stats:
        print("Failed to collect player stats for any position")
        return

    for position, df in position_stats.items():
        print(f"\nProcessing {position} data:")
        print(f"Shape: {df.shape}")
        print(f"Columns: {', '.join(df.columns)}")
        save_to_csv(df, current_week, f"{position}_stats")

    print("Data processing and saving completed for all positions")

if __name__ == "__main__":
    main()