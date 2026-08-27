# Strategus Archive

Automated archive of the [Strategus](https://strategus.appspot.com) Elo rankings. A GitHub Actions workflow scrapes the site daily and commits the results, and a static dashboard lets you browse the archive by date.

## How It Works

- [`strategus-scrape.py`](strategus-scrape.py) runs a headless Chrome session, reads the ranking table, and appends the rows to [`ranking_history.csv`](ranking_history.csv).
- The ranking date is derived from the JSON `timestamp` (UTC), so it's consistent regardless of the host's locale.
- A scheduled GitHub Actions workflow ([`.github/workflows/workflow.yml`](.github/workflows/workflow.yml)) runs the scraper daily and commits any new data.

## Usage

Open [`ckfaraday.github.io/strategus-archive/`](https://ckfaraday.github.io/strategus-archive/) to view the archive. It fetches the CSV and lets you pick a date to display that day's rankings.

## Requirements

- Python 3.12+
- Selenium

## Local Usage

```bash
pip install -r requirements.txt
python strategus-scrape.py
```
This appends the ranking data from strategus.appspot.com and appends them to the ranking_history.csv file if it does not already exist.
