import pandas as pd
import re

TEAM_NAME_MAPPING = {
    'sanfrancisco49ers': '49ers', 'dallascowboys': 'cowboys', 'philadelphiaeagles': 'eagles',
    'buffalobills': 'bills', 'newyorkjets': 'jets', 'newenglandpatriots': 'patriots',
    'baltimoreravens': 'ravens', 'denverbroncos': 'broncos', 'pittsburghsteelers': 'steelers',
    'neworleanssaints': 'saints', 'kansascitychiefs': 'chiefs', 'miamidolphins': 'dolphins',
    'washingtoncommanders': 'commanders', 'cincinnatibengals': 'bengals', 'clevelandbrowns': 'browns',
    'greenbaypackers': 'packers', 'losangeleschargers': 'chargers', 'jacksonvillejaguars': 'jaguars',
    'tampabaybuccaneers': 'buccaneers', 'seattleseahawks': 'seahawks', 'indianapoliscolts': 'colts',
    'carolinapanthers': 'panthers', 'tennesseetitans': 'titans', 'newyorkgiants': 'giants',
    'detroitlions': 'lions', 'losangelesrams': 'rams', 'minnesotavikings': 'vikings',
    'atlantafalcons': 'falcons', 'arizonacardinals': 'cardinals', 'houstontexans': 'texans',
    'chicagobears': 'bears', 'lasvegasraiders': 'raiders'
}

def transform_fantasy_pros_data(df: pd.DataFrame) -> pd.DataFrame:
    df['player_name'] = df['player_name'].apply(lambda name: re.sub(r"(?:I{1,3}|IV|V?I{0,3}|Jr|Sr)\s*$", "", name).strip().lower().replace(' ', ''))
    df['player_team_id'] = df['player_team_id'].map(TEAM_NAME_MAPPING).fillna(df['player_team_id'])
    return df[['player_name', 'player_team_id', 'player_position_id', 'rank_ecr', 'pos_rank']]