from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from datetime import datetime
import json
import csv
import os
import time
import logging

# CSV headers
RANKING_CSV_HEADER = ['date', 'pos', 'name', 'flag', 'score', 'diff', 'wld', 'eff', 'opps', 'aor']
HIGHLIGHTS_CSV_HEADER = ['date', 'metric', 'player_count', 'players_json']
MATCH_CSV_HEADER = ['date', 'player1', 'player2', 'result', 'moves', 'elo_change1', 'elo_change2']

MAX_RETRIES = 3
PAGE_LOAD_TIMEOUT = 30

def _setup_logging():
    """Configure terminal-only logging in a Rose-style format"""
    class _Fmt(logging.Formatter):
        def format(self, record):
            record._when = time.strftime("%H:%M:%S", time.localtime())
            return super().format(record)

    logger = logging.getLogger("scrape")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_Fmt("%(_when)s | %(levelname)-7s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

log = _setup_logging()

def log_success(message, tag="SCRAPE"):
    """Log a success line in Rose-style format"""
    log.info(f"[{tag}] {message}")

def log_event(event, details=None, icon="", tag="SCRAPE"):
    """Log an event line, optionally followed by indented details"""
    log.info(f"{icon} [{tag}] {event}" if icon else f"[{tag}] {event}")
    if details:
        for key, value in details.items():
            log.info(f"   | {key}: {value}")

def log_section(title, tag="SCRAPE"):
    """Log a section header"""
    log.info(f"--- {title} ---")

def log_status(status, value, tag="SCRAPE"):
    """Log a status line"""
    log.info(f"[{tag}] {status}: {value}")

def ensure_csv_header(filename, header):
    """Ensure CSV file exists with correct header"""
    if not os.path.isfile(filename):
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(header)

def date_from_timestamp(driver, json_url):
    """Fetch the JSON timestamp and return a deterministic UTC date YYYY-MM-DD"""
    driver.get(json_url)
    body = driver.execute_script("return document.body.innerText")
    data = json.loads(body)
    ts_ms = data["timestamp"]
    return datetime.utcfromtimestamp(ts_ms / 1000.0).strftime('%Y-%m-%d')

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

def create_driver():
    """Create a shared headless Chrome driver"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver

def scrape_ranking_data(driver, url, scraped_date):
    """Scrape the ranking table data"""
    data = []

    driver.get(url)

    # Click "Show all" button if exists
    try:
        show_all_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "divShowAll"))
        )
        show_all_button.click()
        time.sleep(2)
        log_success("Expanded 'Show all' list")
    except TimeoutException:
        log.warning("[SCRAPE] 'Show all' button not found; may get incomplete ranking")
    except Exception as e:
        log.warning(f"[SCRAPE] could not click 'Show all': {e}")

    # Scrape table data
    table_body = driver.find_element(By.ID, "listing")
    rows = table_body.find_elements(By.TAG_NAME, "tr")

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) >= 9:
            pos = cols[0].text.strip()
            name = cols[1].text.strip()

            try:
                flag_span = cols[2].find_element(By.TAG_NAME, "span")
                flag = flag_span.get_attribute("class").replace("flag ", "").replace("flag-", "").upper()
            except Exception:
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

def scrape_highlights_data(driver, url, scraped_date):
    """Scrape highlights data with robust waiting"""
    driver.get(url)

    # Wait for JavaScript to execute and content to load
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#highlights ul li"))
    )

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

def scrape_match_data(driver, url, scraped_date):
    """Scrape match results data with numeric results (1=player1 won, 2=player2 won, draw)"""
    matches = []

    driver.get(url)

    # Wait for JavaScript to execute and content to load
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#results tr"))
    )

    # Scrape all match rows
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
            log.debug(f"[SCRAPE] error processing match row: {e}")
            continue

    return matches

def scrape_with_retry(scrape_func, driver, url, scraped_date):
    """Run a scrape with retries on transient failures"""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return scrape_func(driver, url, scraped_date)
        except Exception as e:
            last_error = e
            log.warning(f"[SCRAPE] attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                # Recreate the driver in case the session is in a bad state
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = create_driver()
                time.sleep(2)
    raise last_error

def save_to_csv(data, filename, header):
    """Save data to CSV, checking for duplicates"""
    if not data:
        return

    ensure_csv_header(filename, header)

    # Get the date from the first row of new data
    new_date = data[0][0] if data else None

    # Check if this date already exists in the file
    if new_date and is_date_already_saved(new_date, filename):
        log.info(f"[SCRAPE] data for {new_date} already exists in {filename}. Skipping.")
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

    ranking_url = "https://strategus.appspot.com/eloRanking.html"
    ranking_json_url = "https://strategus.appspot.com/eloRanking"
    highlights_url = "https://strategus.appspot.com/rankedResults.html"
    highlights_json_url = "https://strategus.appspot.com/rankedResults"
    ranking_csv = 'ranking_history.csv'
    highlights_csv = 'highlights_history.csv'
    match_csv = 'match_history.csv'

    log_section("Strategus Archive Scrape")

    driver = None
    try:
        driver = create_driver()
        log_success("Launched headless browser")

        # Scrape and save ranking data
        log_section("Rankings")
        ranking_date = date_from_timestamp(driver, ranking_json_url)
        log_status("ranking date", ranking_date)
        ranking_data = scrape_with_retry(scrape_ranking_data, driver, ranking_url, ranking_date)
        if ranking_data:
            log_event("ranking data", {"rows": len(ranking_data)})
            save_to_csv(ranking_data, ranking_csv, RANKING_CSV_HEADER)

        # Scrape and save highlights data
        log_section("Highlights")
        highlights_date = date_from_timestamp(driver, highlights_json_url)
        log_status("highlights date", highlights_date)
        highlights_data = scrape_with_retry(scrape_highlights_data, driver, highlights_url, highlights_date)
        if highlights_data:
            log_event("highlights data", {"rows": len(highlights_data)})
            save_to_csv(highlights_data, highlights_csv, HIGHLIGHTS_CSV_HEADER)

        # Scrape and save match data
        log_section("Matches")
        match_data = scrape_with_retry(scrape_match_data, driver, highlights_url, highlights_date)
        if match_data:
            log_event("match data", {"rows": len(match_data)})
            save_to_csv(match_data, match_csv, MATCH_CSV_HEADER)

    finally:
        if driver is not None:
            try:
                driver.quit()
                log.info("[SCRAPE] browser closed")
            except Exception:
                pass

    log_success("Scraping complete")
