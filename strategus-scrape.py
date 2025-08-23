from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import json
import csv
import os
import time

# CSV headers
RANKING_CSV_HEADER = ['date', 'pos', 'name', 'flag', 'score', 'diff', 'wld', 'eff', 'opps', 'aor']
HIGHLIGHTS_CSV_HEADER = ['date', 'metric', 'player_count', 'players_json']
MATCH_CSV_HEADER = ['date', 'player1', 'player2', 'result', 'moves', 'elo_change1', 'elo_change2']

def ensure_csv_header(filename, header):
    """Ensure CSV file exists with correct header"""
    if not os.path.isfile(filename):
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(header)

def parse_date(date_text):
    """Parse date from text"""
    try:
        if "Last updated:" in date_text:
            date_text = date_text.split("Last updated:")[1].strip()
        date_part = date_text.split(',')[0].strip()
        day, month, year = map(int, date_part.split('/'))
        return f"{year}-{month:02d}-{day:02d}"
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')

def parse_highlight_item(text, metric):
    """Parse individual highlight item"""
    details = text.split(':', 1)[1].strip()
    players = []
    
    if metric in ['All-time-high Elo hits', 'Biggest Elo rise', 'Biggest Elo drop']:
        for entry in details.split(','):
            entry = entry.strip()
            if '(' in entry:
                name, elo = entry.split('(')
                players.append({
                    'name': name.strip(),
                    'elo': elo.replace(')', '').strip()
                })
    
    elif metric in ['Best W-L streak', 'Worst W-L streak']:
        for entry in details.split(','):
            entry = entry.strip()
            if '(' in entry:
                name, stats = entry.split('(')
                stats = stats.replace(')', '')
                if '-' in stats:
                    wins, losses = stats.split('-')
                    players.append({
                        'name': name.strip(),
                        'wins': wins.replace('W', '').strip(),
                        'losses': losses.replace('L', '').strip()
                    })
    
    elif metric == 'Prolonged win streaks':
        for entry in details.split(','):
            entry = entry.strip()
            if '(' in entry:
                name, wins = entry.split('(')
                players.append({
                    'name': name.strip(),
                    'wins': wins.replace('W', '').replace(')', '').strip()
                })
    
    elif metric == 'Most active player':
        for entry in details.split(','):
            entry = entry.strip()
            if '(' in entry:
                name, games = entry.split('(')
                players.append({
                    'name': name.strip(),
                    'games': games.replace('games', '').replace(')', '').strip()
                })
    
    else:  # New players, Comebacks
        for entry in details.split(','):
            if entry.strip():
                players.append({'name': entry.strip()})
    
    return players

def scrape_ranking_data(url):
    """Scrape the ranking table data"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(url)
        
        # Click "Show all" button if exists
        try:
            show_all_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "divShowAll"))
            )
            show_all_button.click()
            time.sleep(2)
        except Exception:
            pass
        
        # Get date
        date_span = driver.find_element(By.ID, "txtInfo")
        scraped_date = parse_date(date_span.text)
        
        # Scrape table data
        table_body = driver.find_element(By.ID, "listing")
        rows = table_body.find_elements(By.TAG_NAME, "tr")
        
        data = []
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 9:
                pos = cols[0].text.strip()
                name = cols[1].text.strip()
                
                try:
                    flag_span = cols[2].find_element(By.TAG_NAME, "span")
                    flag = flag_span.get_attribute("class").replace("flag ", "").replace("flag-", "").upper()
                except:
                    flag = ""
                
                data.append([
                    scraped_date,
                    pos,
                    name,
                    flag,
                    cols[3].text.strip(),
                    cols[4].text.strip().replace('(', '').replace(')', '').replace('d', '').strip(),
                    cols[5].text.strip(),
                    cols[6].text.strip(),
                    cols[7].text.strip(),
                    cols[8].text.strip()
                ])
        
        return data
    finally:
        driver.quit()

def scrape_highlights_data(url):
    """Scrape highlights data with robust waiting"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(url)
        
        # Wait for JavaScript to execute and content to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#highlights ul li"))
        )
        
        date_span = driver.find_element(By.ID, "txtInfo")
        scraped_date = parse_date(date_span.text)
        
        highlights_items = driver.find_elements(By.CSS_SELECTOR, "#highlights ul li")
        
        data = []
        for item in highlights_items:
            text = item.text.strip()
            if not text or ':' not in text:
                continue
                
            metric = text.split(':')[0].strip()
            players = parse_highlight_item(text, metric)
            
            if players:
                data.append([
                    scraped_date,
                    metric,
                    len(players),
                    json.dumps(players, ensure_ascii=False)
                ])
        
        return data
    finally:
        driver.quit()

def scrape_match_data(url):
    """Scrape match results data with numeric results (1=player1 won, 2=player2 won, draw)"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(url)
        
        # Wait for JavaScript to execute and content to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#results tr"))
        )
        
        # Get the date from the page
        date_span = driver.find_element(By.ID, "txtInfo")
        scraped_date = parse_date(date_span.text)
        
        # Scrape all match rows
        matches = []
        rows = driver.find_elements(By.CSS_SELECTOR, "#results tr")
        
        for row in rows:
            try:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 4:  # Skip if not enough columns
                    continue
                
                # Skip incognito matches (marked with "[?]" in second column)
                if cols[1].text.strip() == "[?]":
                    continue
                
                # Parse the match info
                vs_text = cols[0].text.strip()
                if " vs. " not in vs_text:
                    continue
                
                # Split player info and results
                player1_part, player2_part = vs_text.split(" vs. ")
                
                # Extract player1 name and result
                if "[" in player1_part:
                    player1, result1 = player1_part.rsplit(" [", 1)
                    result1 = result1.replace("]", "").strip()
                else:
                    player1 = player1_part.strip()
                    result1 = ""
                
                # Extract player2 name and result
                if "[" in player2_part:
                    player2, result2 = player2_part.rsplit(" [", 1)
                    result2 = result2.replace("]", "").strip()
                else:
                    player2 = player2_part.strip()
                    result2 = ""
                
                # Determine match result
                if result1 == "W" and result2 == "L":
                    result = "1"  # player1 won
                elif result1 == "L" and result2 == "W":
                    result = "2"  # player2 won
                else:
                    result = "draw"
                
                # Get moves count
                moves = cols[2].text.strip()
                
                # Get ELO changes (split by slash and clean)
                elo_changes = cols[3].text.strip().split("/")
                if len(elo_changes) == 2:
                    elo_change1 = elo_changes[0].strip()
                    elo_change2 = elo_changes[1].strip()
                else:
                    elo_change1 = ""
                    elo_change2 = ""
                
                matches.append([
                    scraped_date,
                    player1.strip(),
                    player2.strip(),
                    result,
                    moves,
                    elo_change1,
                    elo_change2
                ])
                
            except Exception as e:
                print(f"Error processing row: {e}")
                continue
        
        return matches
    
    except Exception as e:
        print(f"Error in match scraping: {e}")
        return None
    finally:
        driver.quit()

def save_to_csv(data, filename, header):
    """Save data to CSV, checking for duplicates"""
    if not data:
        return
    
    ensure_csv_header(filename, header)
    
    # Get the date from the first row of new data
    new_date = data[0][0] if data else None
    
    # Check if this date already exists in the file
    if new_date and is_date_already_saved(new_date, filename):
        print(f"Data for date {new_date} already exists in {filename}. Skipping.")
        return
    
    # If not, append the new data
    with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(data)

def is_date_already_saved(date_to_check, filename):
    """Check if date exists in CSV"""
    if not os.path.isfile(filename):
        return False
    
    with open(filename, 'r', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        next(reader, None)  # Skip header
        for row in reader:
            if row and row[0] == date_to_check:
                return True
    return False

if __name__ == "__main__":
    # Initialize CSVs
    ensure_csv_header('ranking_history.csv', RANKING_CSV_HEADER)
    ensure_csv_header('highlights_history.csv', HIGHLIGHTS_CSV_HEADER)
    ensure_csv_header('match_history.csv', MATCH_CSV_HEADER)
    
    # Scrape and save ranking data
    ranking_url = "https://strategus.appspot.com/eloRanking.html"
    ranking_data = scrape_ranking_data(ranking_url)
    if ranking_data:
        save_to_csv(ranking_data, 'ranking_history.csv', RANKING_CSV_HEADER)
    
    # Scrape and save highlights data
    highlights_url = "https://strategus.appspot.com/rankedResults.html"
    highlights_data = scrape_highlights_data(highlights_url)
    if highlights_data:
        save_to_csv(highlights_data, 'highlights_history.csv', HIGHLIGHTS_CSV_HEADER)
    
    # Scrape and save match data
    match_data = scrape_match_data(highlights_url)  # Using same URL as highlights
    if match_data:
        save_to_csv(match_data, 'match_history.csv', MATCH_CSV_HEADER)
    
    print("Scraping complete!")