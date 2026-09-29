"""Market News Data Cleaner.

Reads raw crawled market news (or fallback if raw is missing),
removes duplicates, filters null or malformed records,
standardizes dates, and saves to data/processed/cleaned_market_news.csv.
"""

import os
import sys
import re
import csv
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw", "crawled_market_news.csv")
FALLBACK_DATA_PATH = os.path.join(BASE_DIR, "data", "fallback", "fallback_market_news.csv")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
CLEANED_DATA_PATH = os.path.join(PROCESSED_DIR, "cleaned_market_news.csv")
LOG_PATH = os.path.join(BASE_DIR, "logs", "cleaner.log")

os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("cleaner")


def clean_data() -> Tuple[str, List[Dict[str, Any]], Dict[str, int]]:
    """Cleans raw market news data and saves to data/processed/cleaned_market_news.csv.

    Returns:
        (status, cleaned_records, stats)
    """
    source_path = RAW_DATA_PATH
    used_fallback_input = False

    if not os.path.exists(RAW_DATA_PATH) or os.path.getsize(RAW_DATA_PATH) == 0:
        logger.warning(f"Raw data not found or empty at {RAW_DATA_PATH}. Using fallback dataset.")
        source_path = FALLBACK_DATA_PATH
        used_fallback_input = True

    if not os.path.exists(source_path):
        logger.error(f"Neither raw nor fallback file found at {source_path}")
        return "FAILED", [], {"initial": 0, "cleaned": 0, "dropped": 0}

    logger.info(f"Loading data from {source_path} for cleaning...")
    cleaned_rows = []
    seen_titles = set()
    seen_urls = set()
    total_input = 0
    dropped_empty = 0
    dropped_duplicates = 0

    try:
        with open(source_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                total_input += 1
                title = (row.get("title") or "").strip()
                url = (row.get("source_url") or "").strip()
                summary = (row.get("summary") or "").strip()

                # Filter out empty or too short titles
                if not title or len(title) < 4:
                    dropped_empty += 1
                    continue

                # Deduplicate by normalized title and URL
                norm_title = re.sub(r"\s+", "", title).lower()
                if norm_title in seen_titles:
                    dropped_duplicates += 1
                    continue
                if url and url in seen_urls:
                    dropped_duplicates += 1
                    continue

                seen_titles.add(norm_title)
                if url:
                    seen_urls.add(url)

                # Standardize date format YYYY-MM-DD
                raw_date = (row.get("date") or "").strip()
                if len(raw_date) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", raw_date):
                    date = raw_date[:10]
                else:
                    date = datetime.now().strftime("%Y-%m-%d")

                row_cleaned = dict(row)
                row_cleaned["title"] = title
                row_cleaned["date"] = date
                row_cleaned["summary"] = summary
                row_cleaned["has_null"] = "false" if (title and summary) else "true"
                row_cleaned["is_duplicate_seed"] = "false"
                if "data_origin" not in row_cleaned or not row_cleaned["data_origin"]:
                    row_cleaned["data_origin"] = "synthetic_fallback" if used_fallback_input else "live"

                cleaned_rows.append(row_cleaned)

        if not cleaned_rows:
            logger.warning("Cleaning resulted in 0 rows.")
            return "WARNING", [], {"initial": total_input, "cleaned": 0, "dropped": total_input}

        fieldnames = [
            "article_id", "category", "title", "date", "content", "summary",
            "source_url", "source_name", "company_tag", "keywords",
            "collected_at", "has_null", "is_duplicate_seed", "data_origin"
        ]

        with open(CLEANED_DATA_PATH, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in cleaned_rows:
                writer.writerow({k: r.get(k, "") for k in fieldnames})

        stats = {
            "initial": total_input,
            "cleaned": len(cleaned_rows),
            "dropped_duplicates": dropped_duplicates,
            "dropped_empty": dropped_empty
        }
        logger.info(f"Cleaned {len(cleaned_rows)} records successfully. Saved to {CLEANED_DATA_PATH}")
        status = "WARNING" if used_fallback_input else "SUCCESS"
        return status, cleaned_rows, stats

    except Exception as e:
        logger.error(f"Error during data cleaning: {e}")
        return "FAILED", [], {"initial": total_input, "cleaned": 0, "error": str(e)}


def main() -> None:
    """CLI execution for cleaning."""
    status, rows, stats = clean_data()
    print("\n" + "=" * 50)
    print("CLEANER EXECUTION SUMMARY")
    print("=" * 50)
    print(f"Status        : {status}")
    print(f"Input Records : {stats.get('initial', 0)}")
    print(f"Cleaned Total : {len(rows)}")
    print(f"Duplicates    : {stats.get('dropped_duplicates', 0)}")
    print(f"Output File   : {CLEANED_DATA_PATH}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
