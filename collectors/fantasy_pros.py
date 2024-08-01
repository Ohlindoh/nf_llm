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

def collect_fantasy_pros_data():
    base_url = 'http://www.fantasypros.com/nfl/rankings'
    rankings_list = ['qb', 'ppr-rb', 'ppr-wr', 'ppr-te', 'dst']
    
    all_data = []
    for page in rankings_list:
        url = f'{base_url}/{page}.php'
        logging.info(f"Fetching data from {url}")
        html_content = fetch_fantasy_pros_data(url)
        if html_content:
            data = parse_fantasy_pros_data(html_content)
            if data and 'players' in data:
                all_data.extend(data['players'])
            else:
                logging.warning(f"No valid data found for {url}")
        else:
            logging.warning(f"Failed to fetch data from {url}")
    
    if not all_data:
        logging.error("No data collected")
        return None
    
    return pd.DataFrame(all_data)