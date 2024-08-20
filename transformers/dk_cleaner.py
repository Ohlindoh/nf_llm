# transformers/dk_cleaner.py

import pandas as pd
from typing import Dict, Any, Optional

def clean_player_name(first_name: str, last_name: str) -> str:
    """
    Clean and combine player's first and last name.
    
    Args:
        first_name (str): Player's first name.
        last_name (str): Player's last name.
    
    Returns:
        str: Cleaned and combined player name.
    """
    # Remove spaces and convert to lowercase
    first_name = first_name.replace(" ", "").lower()
    last_name = last_name.replace(" ", "").lower()
    
    # Remove suffixes from last name
    last_name = pd.Series(last_name).str.replace(r"(?:I{1,3}|IV|V?I{0,3})\s*$", "", regex=True).str.replace(r"(jr|sr)\s*$", "", regex=True).iloc[0]
    
    return f"{first_name}{last_name}"

def process_draftkings_data(data: Optional[Dict[str, Any]]) -> Optional[pd.DataFrame]:
    """
    Process and clean DraftKings data.
    
    Args:
        data (Optional[Dict[str, Any]]): Raw DraftKings data.
    
    Returns:
        Optional[pd.DataFrame]: Processed DataFrame with player names and salaries, or None if processing fails.
    """
    if not data or 'draftables' not in data:
        return None

    try:
        player_list = [
            {
                'player_name': clean_player_name(player['firstName'], player['lastName']),
                'salary': player['salary']
            } 
            for player in data['draftables']
        ]
        
        df = pd.DataFrame(player_list)
        return df.drop_duplicates('player_name')
    
    except KeyError as e:
        print(f"Error: Missing expected key in data structure: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error occurred while processing DraftKings data: {e}")
        return None