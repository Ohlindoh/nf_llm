# transformers/draftkings_cleaner.py

import pandas as pd

def process_draftkings_data(data):
    if not data or 'draftables' not in data:
        return None

    player_list = [{'firstName': player['firstName'].replace(" ", ""), 
                    'lastName': player['lastName'].replace(" ", ""), 
                    'salary': player['salary']} for player in data['draftables']]
    df = pd.DataFrame(player_list)
    df['lastName'] = df['lastName'].str.replace(r"(?:I{1,3}|IV|V?I{0,3})\s*$", " ", regex=True)
    df['lastName'] = df['lastName'].str.replace(r"(Jr|Sr)\s*$", " ", regex=True)
    df["player_name"] = df['firstName'].astype(str) + df["lastName"]
    df['player_name'] = df.player_name.str.lower().replace('\s+', '', regex=True) # type: ignore
    return df[['player_name', 'salary']].drop_duplicates('player_name')