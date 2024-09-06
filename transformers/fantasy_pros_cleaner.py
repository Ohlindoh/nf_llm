import pandas as pd
import logging
import re
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = 'data'
OUTPUT_FILE = 'cleaned_fantasy_projections.csv'

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

def clean_player_name(name: str) -> str:
    """Clean player name for consistent matching."""
    return re.sub(r'[^a-zA-Z]', '', name).lower()

def transform_fantasy_pros_data(data: pd.DataFrame) -> pd.DataFrame:
    logger.info("Transforming Fantasy Pros data")
    logger.info(f"Input data shape: {data.shape}")
    logger.info(f"Input data columns: {data.columns.tolist()}")

    try:
        # Check if 'player_name' is in the input data
        if 'player_name' not in data.columns:
            logger.error("'player_name' column not found in input data")
            return pd.DataFrame()

        # Ensure required columns are present
        required_columns = ['player_name', 'player_team_id', 'player_position_id', 'rank_ecr', 'pos_rank', 'projected_points']
        for col in required_columns:
            if col not in data.columns:
                logger.error(f"Required column '{col}' not found in Fantasy Pros data")
                return pd.DataFrame()

        # Select and rename columns
        df = data[required_columns].copy()

        # Clean player names
        df['player_name'] = df['player_name'].apply(clean_player_name)

        logger.info(f"Transformed data shape: {df.shape}")
        logger.info(f"Transformed data columns: {df.columns.tolist()}")
        return df

    except Exception as e:
        logger.error(f"Error transforming Fantasy Pros data: {str(e)}")
        return pd.DataFrame()

def save_cleaned_data(df: pd.DataFrame) -> None:
    """Save the cleaned Fantasy Pros data to a CSV file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    df.to_csv(output_path, index=False)
    logger.info(f"Cleaned Fantasy Pros data saved to {output_path}")

if __name__ == "__main__":
    # This is for testing purposes
    from fantasy_pros_projections import collect_fantasy_pros_data
    
    raw_data = collect_fantasy_pros_data()
    if not raw_data.empty:
        cleaned_data = transform_fantasy_pros_data(raw_data)
        if not cleaned_data.empty:
            save_cleaned_data(cleaned_data)
            print("Data cleaning and saving completed successfully.")
            print(cleaned_data.head())
            print(f"Total players after cleaning: {len(cleaned_data)}")
            print(f"Columns after cleaning: {cleaned_data.columns.tolist()}")
        else:
            print("Data cleaning failed.")
    else:
        print("No data to clean.")