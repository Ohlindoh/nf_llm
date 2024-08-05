# player_stats_collector.py

import requests
import pandas as pd
import bs4
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_fantasy_pros_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"Error fetching data from {url}: {e}")
        return None

def parse_fantasy_pros_table(html_content):
    soup = bs4.BeautifulSoup(html_content, "html.parser")
    table = soup.find('table', {'id': 'data'})
    
    if not table:
        logging.warning("No table found in the HTML content")
        return None

    headers = [header.text.strip() for header in table.find_all('th')] # type: ignore
    rows = table.find_all('tr') # type: ignore
    player_stats = []

    for row in rows[1:]:  # Skip the header row
        if isinstance(row, bs4.element.Tag):
            cols = row.find_all('td')
            if cols:
                cols = [col.text.strip() for col in cols]
                player_stats.append(cols)

    df = pd.DataFrame(player_stats, columns=headers)
    return df

def get_position_data(position, week):
    url = f'https://www.fantasypros.com/nfl/stats/{position.lower()}.php?range=week&week={week}'
    html_content = fetch_fantasy_pros_data(url)
    if html_content:
        df = parse_fantasy_pros_table(html_content)
        if df is not None:
            df['Position'] = position
            return df
    return None

def collect_player_stats(week):
    positions = ['QB', 'RB', 'WR', 'TE', 'DST']
    all_data = []

    for position in positions:
        position_data = get_position_data(position, week)
        if position_data is not None:
            position_data.columns = [col.strip() for col in position_data.columns]
            all_data.append(position_data)
            logging.info(f"{position} data processed successfully")
        else:
            logging.error(f"Failed to process {position} data")

    if all_data:
        # Find common columns
        common_columns = list(set.intersection(*(set(df.columns) for df in all_data)))
        
        # Ensure all DataFrames have the same columns before concatenation
        all_data_aligned = [df[common_columns] for df in all_data]
        
        combined_data = pd.concat(all_data_aligned, ignore_index=True)
        logging.info("All stats collected successfully")
        return combined_data
    else:
        logging.error("No data collected")
        return None