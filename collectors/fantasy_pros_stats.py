# player_stats_collector.py

import requests
import pandas as pd
import bs4
import re
import json
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

def parse_fantasy_pros_data(html_content):
    soup = bs4.BeautifulSoup(html_content, "html.parser")
    scripts = soup.find_all("script")
    for script in scripts:
        if script.string:
            match = re.search(r"var ecrData = ({.*?});\s*", script.string, re.DOTALL)
            if match:
                return json.loads(match.group(1))
    logging.warning("No ecrData found in the HTML content")
    return None

def get_position_data(position):
    url = f'https://www.fantasypros.com/nfl/stats/{position.lower()}.php'
    html_content = fetch_fantasy_pros_data(url)
    if html_content:
        data = parse_fantasy_pros_data(html_content)
        if data and 'players' in data:
            df = pd.DataFrame(data['players'])
            df['position'] = position
            return df
    return None

def collect_player_stats():
    positions = ['QB', 'RB', 'WR', 'TE', 'DST']
    all_data = []

    for position in positions:
        position_data = get_position_data(position)
        if position_data is not None:
            all_data.append(position_data)
            logging.info(f"{position} data processed successfully")
        else:
            logging.error(f"Failed to process {position} data")

    if all_data:
        combined_data = pd.concat(all_data, ignore_index=True)
        logging.info("All stats collected successfully")
        return combined_data
    else:
        logging.error("No data collected")
        return None

if __name__ == "__main__":
    stats = collect_player_stats()
    if stats is not None:
        print(stats.head())