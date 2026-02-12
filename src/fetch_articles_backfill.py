import requests
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import logging

API_URL = "https://dev.to/api/articles"
PER_PAGE = 100
STATE = "fresh"
DATA_DIR = Path("data/raw")
LATEST_TIMESTAMP_FILE = Path("data/latest_timestamp.json")
START_DATE = datetime.fromisoformat("2023-01-01T00:00:00+00:00")
SLEEP_DELAY = 2
MAX_RETRIES = 3  # retries per API call

# Setup logging (works in Azure Functions)
logging.basicConfig(level=logging.INFO)

# Load latest timestamp
if LATEST_TIMESTAMP_FILE.exists():
    with open(LATEST_TIMESTAMP_FILE) as f:
        latest_ts_str = json.load(f).get("latest_timestamp")
        latest_timestamp = datetime.fromisoformat(latest_ts_str)
else:
    latest_timestamp = None

new_articles = []
page = 1
max_ts_seen = latest_timestamp

while True:
    params = {"per_page": PER_PAGE, "page": page, "state": STATE}

    # Retry logic
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # timeout prevents hanging requests in Azure Functions
            response = requests.get(API_URL, params=params, timeout=10)
            response.raise_for_status()
            articles = response.json()
            break  # success, exit retry loop
        except requests.exceptions.RequestException as e:
            logging.warning(f"API request failed (attempt {attempt}): {e}")
            if attempt == MAX_RETRIES:
                logging.error(f"Max retries reached for page {page}. Aborting fetch.")
                articles = []
                break
            time.sleep(2**attempt)  # exponential backoff
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON response: {e}")
            articles = []
            break

    if not articles:
        break  # stop if no data or error

    stop_fetching = False
    for article in articles:
        try:
            published_at = datetime.fromisoformat(
                article["published_at"].replace("Z", "+00:00")
            )
        except Exception as e:
            logging.warning(f"Skipping article due to parsing error: {e}")
            continue

        # Incremental load
        if latest_timestamp and published_at <= latest_timestamp:
            continue

        # Historical backfill: stop if article is older than start_date
        if published_at < START_DATE:
            stop_fetching = True
            break

        new_articles.append(article)
        if not max_ts_seen or published_at > max_ts_seen:
            max_ts_seen = published_at

    if stop_fetching:
        break

    time.sleep(SLEEP_DELAY)
    page += 1

# Save new articles
if new_articles:
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_path = DATA_DIR / today_str
    save_path.mkdir(parents=True, exist_ok=True)
    file_path = save_path / f"articles_page_{page-1}.json"

    with open(file_path, "w") as f:
        json.dump(new_articles, f, indent=2)
    logging.info(f"Saved {len(new_articles)} new articles to {file_path}")

    if max_ts_seen:
        with open(LATEST_TIMESTAMP_FILE, "w") as f:
            json.dump({"latest_timestamp": max_ts_seen.isoformat()}, f)
else:
    logging.info("No new articles found.")
