import pandas as pd
import re
from typing import Dict

TEAM_NAME_MAPPING: Dict[str, str] = {
    'sanfrancisco49ers': '49ers',
    'dallascowboys': 'cowboys',
    'philadelphiaeagles': 'eagles',
    'buffalobills': 'bills',
    'newyorkjets': 'jets',
    'newenglandpatriots': 'patriots',
    'baltimoreravens': 'ravens',
    'denverbroncos': 'broncos',
    'pittsburghsteelers': 'steelers',
    'neworleanssaints': 'saints',
    'kansascitychiefs': 'chiefs',
    'miamidolphins': 'dolphins',
    'washingtoncommanders': 'commanders',
    'cincinnatibengals': 'bengals',
    'clevelandbrowns': 'browns',
    'greenbaypackers': 'packers',
    'losangeleschargers': 'chargers',
    'jacksonvillejaguars': 'jaguars',
    'tampabaybuccaneers': 'buccaneers',
    'seattleseahawks': 'seahawks',
    'indianapoliscolts': 'colts',
    'carolinapanthers': 'panthers',
    'tennesseetitans': 'titans',
    'newyorkgiants': 'giants',
    'detroitlions': 'lions',
    'losangelesrams': 'rams',
    'minnesotavikings': 'vikings',
    'atlantafalcons': 'falcons',
    'arizonacardinals': 'cardinals',
    'houstontexans': 'texans',
    'chicagobears': 'bears',
    'lasvegasraiders': 'raiders'
}

def clean_player_name(name: str) -> str:
    """
    Clean player name by removing suffixes and standardizing format.
    
    Args:
        name (str): The original player name.
    
    Returns:
        str: The cleaned player name.
    """
    name = re.sub(r"(?:I{1,3}|IV|V?I{0,3})\s*$", "", name)
    name = re.sub(r"(Jr|Sr)\s*$", "", name)
    return name.strip().lower().replace(' ', '')

def transform_fantasy_pros_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform Fantasy Pros data by cleaning player names and mapping team names.
    
    Args:
        df (pd.DataFrame): The original Fantasy Pros DataFrame.
    
    Returns:
        pd.DataFrame: The transformed DataFrame.
    """
    df['player_name'] = df['player_name'].apply(clean_player_name)
    df['player_team_id'] = df['player_team_id'].map(TEAM_NAME_MAPPING).fillna(df['player_team_id'])
    columns_to_keep = ['player_name', 'player_team_id', 'player_position_id', 'rank_ecr', 'pos_rank']
    return df[columns_to_keep]

def transform_player_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform player stats data by cleaning player names and mapping team names.
    
    Args:
        df (pd.DataFrame): The original player stats DataFrame.
    
    Returns:
        pd.DataFrame: The transformed DataFrame.
    """
    df['player_name'] = df['player_name'].apply(clean_player_name)
    df['player_team_id'] = df['player_team_id'].map(TEAM_NAME_MAPPING).fillna(df['player_team_id'])
    return df