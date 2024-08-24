import pandas as pd

def clean_player_name(first_name: str, last_name: str) -> str:
    first_name = first_name.replace(" ", "").lower()
    last_name = last_name.replace(" ", "").lower()
    last_name = pd.Series(last_name).str.replace(r"(?:I{1,3}|IV|V?I{0,3}|jr|sr)\s*$", "", regex=True).iloc[0]
    return f"{first_name}{last_name}"

def process_draftkings_data(data: dict) -> pd.DataFrame:
    if not data or 'draftables' not in data:
        return pd.DataFrame()

    player_list = [
        {
            'player_name': clean_player_name(player['firstName'], player['lastName']),
            'salary': player['salary']
        } 
        for player in data['draftables']
    ]
    
    return pd.DataFrame(player_list).drop_duplicates('player_name')