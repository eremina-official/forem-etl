import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

API_URL = "https://dev.to/api/articles"
PER_PAGE = 100
STATE = "fresh"
DATA_DIR = Path("data/raw")
LATEST_TIMESTAMP_FILE = Path("data/latest_timestamp.json")
SLEEP_DELAY = 2
MAX_RETRIES = 3  # retries per API call

logging.basicConfig(level=logging.INFO)


def load_latest_timestamp(path: Path) -> datetime | None:
    """Read the latest timestamp written to disk."""
    if not path.exists():
        return None

    with path.open() as file_handle:
        latest_ts_str = json.load(file_handle).get("latest_timestamp")
        if latest_ts_str:
            return datetime.fromisoformat(latest_ts_str)
    return None


def save_latest_timestamp(path: Path, timestamp: datetime | None) -> None:
    if not timestamp:
        return

    with path.open("w") as file_handle:
        json.dump({"latest_timestamp": timestamp.isoformat()}, file_handle)


def fetch_page(page: int) -> list[dict[str, Any]]:
    """Fetch one page of articles with retry logic."""
    params = {"per_page": PER_PAGE, "page": page, "state": STATE}

    # retry logic
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(API_URL, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logging.warning(f"API request failed (attempt {attempt}): {exc}")
            if attempt == MAX_RETRIES:
                logging.error(
                    "Max retries reached for page %s. Aborting fetch.",
                    page,
                )
            else:
                time.sleep(2**attempt)  # exponential backoff
        except json.JSONDecodeError as exc:
            logging.error(f"Failed to parse JSON response: {exc}")
            break
    return []


def collect_new_articles(
    latest_timestamp: datetime | None,
) -> tuple[list[dict[str, Any]], datetime | None, int]:
    """Download all newly published articles since latest_timestamp."""
    new_articles: list[dict[str, Any]] = []
    page = 1
    max_ts_seen = latest_timestamp
    last_page_fetched = 0

    while True:
        articles = fetch_page(page)
        if not articles:
            break

        for article in articles:
            try:
                published_at = datetime.fromisoformat(
                    article["published_at"].replace("Z", "+00:00")
                )
            except (KeyError, ValueError, TypeError) as exc:
                logging.warning(
                    "Skipping article due to parsing error: %s",
                    exc,
                )
                continue

            if latest_timestamp and published_at <= latest_timestamp:
                continue

            new_articles.append(article)
            if not max_ts_seen or published_at > max_ts_seen:
                max_ts_seen = published_at

        last_page_fetched = page
        page += 1
        time.sleep(SLEEP_DELAY)

    return new_articles, max_ts_seen, last_page_fetched


def save_articles(
    new_articles: list[dict[str, Any]],
    max_ts_seen: datetime | None,
    last_page_fetched: int,
) -> None:
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_path = DATA_DIR / today_str
    save_path.mkdir(parents=True, exist_ok=True)

    file_page = last_page_fetched or 1
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = save_path / f"page={file_page}_{timestamp}.json"

    with file_path.open("w") as file_handle:
        json.dump(new_articles, file_handle, indent=2)
    logging.info(f"Saved {len(new_articles)} new articles to {file_path}")

    save_latest_timestamp(LATEST_TIMESTAMP_FILE, max_ts_seen)


def main() -> None:
    latest_timestamp = load_latest_timestamp(LATEST_TIMESTAMP_FILE)
    new_articles, max_ts_seen, last_page_fetched = collect_new_articles(
        latest_timestamp
    )

    if not new_articles:
        logging.info("No new articles found.")
        return

    save_articles(new_articles, max_ts_seen, last_page_fetched)


if __name__ == "__main__":
    # one_hour_earlier = datetime.now(timezone.utc) - timedelta(hours=1)
    # save_latest_timestamp(LATEST_TIMESTAMP_FILE, one_hour_earlier)
    main()
