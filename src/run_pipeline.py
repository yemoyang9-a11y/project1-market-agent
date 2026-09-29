"""End-to-End Orchestrator Pipeline for NovaFactory AI Market Intelligence.

Executes four modular stages in sequence:
  1. 수집 (Collection)     : src.crawler
  2. 정제 (Cleaning)       : src.cleaner
  3. 추천 (Recommendation) : src.recommender
  4. 대시보드 (Dashboard)   : src.build_site

Handles network timeouts, HTTP 403/404, RSS XML parsing errors, and low collection
counts (< 200 items) with automatic fallback data injection.
Records stage statuses (SUCCESS, WARNING, FAILED) to logs/pipeline.log.
"""

import os
import sys
import shutil
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add src directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

LOGS_DIR = os.path.join(BASE_DIR, "logs")
PIPELINE_LOG_PATH = os.path.join(LOGS_DIR, "pipeline.log")
RAW_CSV_PATH = os.path.join(BASE_DIR, "data", "raw", "crawled_market_news.csv")
FALLBACK_CSV_PATH = os.path.join(BASE_DIR, "data", "fallback", "fallback_market_news.csv")
CLEANED_CSV_PATH = os.path.join(BASE_DIR, "data", "processed", "cleaned_market_news.csv")
RECOMMENDED_CSV_PATH = os.path.join(BASE_DIR, "data", "processed", "recommended_market_news.csv")
INDEX_HTML_PATH = os.path.join(BASE_DIR, "docs", "index.html")

os.makedirs(LOGS_DIR, exist_ok=True)

# Logger setup
logger = logging.getLogger("pipeline")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(PIPELINE_LOG_PATH, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def emergency_fallback_injection() -> int:
    """Copies fallback dataset if raw crawling failed completely."""
    logger.warning("Emergency fallback activated: Deploying fallback_market_news.csv to raw data path...")
    if os.path.exists(FALLBACK_CSV_PATH):
        os.makedirs(os.path.dirname(RAW_CSV_PATH), exist_ok=True)
        shutil.copy2(FALLBACK_CSV_PATH, RAW_CSV_PATH)
        logger.info(f"Emergency fallback successfully written to {RAW_CSV_PATH}")
        return 800
    return 0


def run_pipeline() -> Dict[str, Any]:
    """Runs the full intelligence pipeline and tracks stage statuses."""
    kst = timezone(timedelta(hours=9))
    start_time = datetime.now(kst)
    logger.info("==================================================")
    logger.info(">>> STARTING MARKET AGENT PIPELINE RUN <<<")
    logger.info(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S KST')}")
    logger.info("==================================================")

    pipeline_report = {
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S KST"),
        "stages": {},
        "final_status": "SUCCESS"
    }

    # ---------------------------------------------------------
    # STAGE 1: 수집 (Collection)
    # ---------------------------------------------------------
    logger.info("[STAGE 1/4] Starting Data Collection (crawler.py)...")
    try:
        from crawler import run_crawler
        crawl_status, crawl_stats = run_crawler()
        raw_count = crawl_stats.get("total", 0)
        failed_srcs = crawl_stats.get("failed_sources", [])

        # Low count safety check (< 200 items)
        if raw_count < 200:
            logger.warning(f"Raw count ({raw_count}) is below 200. Triggering fallback reinforcement...")
            emergency_fallback_injection()
            crawl_status = "WARNING"
            crawl_stats["fallback_triggered"] = True

        pipeline_report["stages"]["collection"] = {
            "name": "1. 수집 (Collection)",
            "status": crawl_status,
            "output": RAW_CSV_PATH,
            "details": f"Total: {raw_count} (Live: {crawl_stats.get('live', 0)}, Fallback: {crawl_stats.get('fallback', 0)}, Failed Sources: {len(failed_srcs)})"
        }
        logger.info(f"[STAGE 1/4] Status: {crawl_status} (Records: {raw_count})")

    except Exception as e:
        logger.error(f"[STAGE 1/4] Crawler encountered exception: {e}")
        injected = emergency_fallback_injection()
        pipeline_report["stages"]["collection"] = {
            "name": "1. 수집 (Collection)",
            "status": "WARNING" if injected > 0 else "FAILED",
            "output": RAW_CSV_PATH,
            "details": f"Exception occurred ({e}), fallback injected: {injected} rows"
        }

    # ---------------------------------------------------------
    # STAGE 2: 정제 (Cleaning)
    # ---------------------------------------------------------
    logger.info("[STAGE 2/4] Starting Data Cleaning (cleaner.py)...")
    try:
        from cleaner import clean_data
        clean_status, cleaned_records, clean_stats = clean_data()
        cleaned_count = len(cleaned_records)

        pipeline_report["stages"]["cleaning"] = {
            "name": "2. 정제 (Cleaning)",
            "status": clean_status,
            "output": CLEANED_CSV_PATH,
            "details": f"Cleaned: {cleaned_count} (Dropped Duplicates: {clean_stats.get('dropped_duplicates', 0)}, Empty: {clean_stats.get('dropped_empty', 0)})"
        }
        logger.info(f"[STAGE 2/4] Status: {clean_status} (Records: {cleaned_count})")

    except Exception as e:
        logger.error(f"[STAGE 2/4] Cleaner encountered exception: {e}")
        pipeline_report["stages"]["cleaning"] = {
            "name": "2. 정제 (Cleaning)",
            "status": "FAILED",
            "output": CLEANED_CSV_PATH,
            "details": f"Exception: {e}"
        }

    # ---------------------------------------------------------
    # STAGE 3: 추천 (Recommendation)
    # ---------------------------------------------------------
    logger.info("[STAGE 3/4] Starting Recommendation Scoring (recommender.py)...")
    try:
        from recommender import run_recommender
        rec_status, rec_items, rec_stats = run_recommender(top_n=30)
        rec_count = len(rec_items)
        llm_used = rec_stats.get("llm_used", False)

        pipeline_report["stages"]["recommendation"] = {
            "name": "3. 추천 (Recommendation)",
            "status": rec_status,
            "output": RECOMMENDED_CSV_PATH,
            "details": f"Recommended: {rec_count} items (Engine: {'Gemini LLM' if llm_used else 'Rule-Based Engine'})"
        }
        logger.info(f"[STAGE 3/4] Status: {rec_status} (Records: {rec_count}, LLM: {llm_used})")

    except Exception as e:
        logger.error(f"[STAGE 3/4] Recommender encountered exception: {e}")
        pipeline_report["stages"]["recommendation"] = {
            "name": "3. 추천 (Recommendation)",
            "status": "FAILED",
            "output": RECOMMENDED_CSV_PATH,
            "details": f"Exception: {e}"
        }

    # ---------------------------------------------------------
    # STAGE 4: 대시보드 (Dashboard)
    # ---------------------------------------------------------
    logger.info("[STAGE 4/4] Starting Dashboard Generation (build_site.py)...")
    try:
        from build_site import run_build_site
        site_status, site_stats = run_build_site()

        pipeline_report["stages"]["dashboard"] = {
            "name": "4. 대시보드 (Dashboard)",
            "status": site_status,
            "output": INDEX_HTML_PATH,
            "details": f"Generated HTML: {INDEX_HTML_PATH} (Items: {site_stats.get('total_items', 0)})"
        }
        logger.info(f"[STAGE 4/4] Status: {site_status}")

    except Exception as e:
        logger.error(f"[STAGE 4/4] Site builder encountered exception: {e}")
        pipeline_report["stages"]["dashboard"] = {
            "name": "4. 대시보드 (Dashboard)",
            "status": "FAILED",
            "output": INDEX_HTML_PATH,
            "details": f"Exception: {e}"
        }

    # ---------------------------------------------------------
    # FINAL VERIFICATION & SUMMARY
    # ---------------------------------------------------------
    end_time = datetime.now(kst)
    duration = (end_time - start_time).total_seconds()
    pipeline_report["end_time"] = end_time.strftime("%Y-%m-%d %H:%M:%S KST")
    pipeline_report["duration_seconds"] = round(duration, 2)

    # Determine overall status
    statuses = [s["status"] for s in pipeline_report["stages"].values()]
    if "FAILED" in statuses:
        pipeline_report["final_status"] = "FAILED"
    elif "WARNING" in statuses:
        pipeline_report["final_status"] = "WARNING"
    else:
        pipeline_report["final_status"] = "SUCCESS"

    # Verify all 4 target artifacts exist
    artifacts = [
        ("Raw CSV", RAW_CSV_PATH, os.path.exists(RAW_CSV_PATH) and os.path.getsize(RAW_CSV_PATH) > 0),
        ("Cleaned CSV", CLEANED_CSV_PATH, os.path.exists(CLEANED_CSV_PATH) and os.path.getsize(CLEANED_CSV_PATH) > 0),
        ("Recommended CSV", RECOMMENDED_CSV_PATH, os.path.exists(RECOMMENDED_CSV_PATH) and os.path.getsize(RECOMMENDED_CSV_PATH) > 0),
        ("Dashboard HTML", INDEX_HTML_PATH, os.path.exists(INDEX_HTML_PATH) and os.path.getsize(INDEX_HTML_PATH) > 0)
    ]
    pipeline_report["artifacts"] = {name: path for name, path, exists in artifacts if exists}

    # Print clean formatted console summary
    print("\n" + "=" * 65)
    print("           PIPELINE EXECUTION SUMMARY REPORT")
    print("=" * 65)
    print(f"Overall Status   : [{pipeline_report['final_status']}]")
    print(f"Execution Time   : {pipeline_report['duration_seconds']}s")
    print(f"Pipeline Log     : {PIPELINE_LOG_PATH}")
    print("-" * 65)
    for key, stage in pipeline_report["stages"].items():
        status_tag = f"[{stage['status']}]"
        print(f"{stage['name']:<24} {status_tag:<10} {stage['details']}")
    print("-" * 65)
    print("Generated Artifacts:")
    for name, path, ok in artifacts:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name:<18} : {path}")
    print("=" * 65 + "\n")

    logger.info(f"Pipeline finished with status [{pipeline_report['final_status']}] in {duration:.2f}s")
    return pipeline_report


def main() -> None:
    """CLI execution entrypoint."""
    report = run_pipeline()
    if report["final_status"] == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    main()
