"""Market Intelligence & Competitor Data Crawler.

Collects public market, competitor, tech, and policy news via RSS feeds
and public endpoints without requiring login.
Supports fault-tolerant fallback data merging when live data is insufficient.
"""

import os
import sys
import re
import csv
import html
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Tuple, Optional

# Setup directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "company_profile.yaml")
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw", "crawled_market_news.csv")
FALLBACK_DATA_PATH = os.path.join(BASE_DIR, "data", "fallback", "fallback_market_news.csv")
LOG_PATH = os.path.join(BASE_DIR, "logs", "crawler.log")

# Setup Logging
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "data", "raw"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("crawler")


def load_company_profile(config_path: str) -> Dict[str, Any]:
    """Loads company profile configuration safely."""
    try:
        import yaml
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load {config_path} with pyyaml: {e}. Using fallback defaults.")

    # Minimal default profile if loading fails
    return {
        "company_name": "NovaFactory AI",
        "business_area": "제조업 AI 비전 품질검사",
        "competitors": ["VisionForge", "InspectAI", "FactoryMind", "QualiBot"],
        "interest_keywords": ["AI", "스마트팩토리", "품질검사", "자동화", "클라우드", "제조 AX"],
        "funding_keywords": ["창업지원", "AI 바우처", "스마트공장", "R&D", "사업화 자금"]
    }


def clean_html_text(raw_text: Optional[str]) -> str:
    """Removes HTML tags and unescapes entities."""
    if not raw_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(date_str: Optional[str]) -> str:
    """Parses various date formats to YYYY-MM-DD."""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    date_str = date_str.strip()
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Try common formats
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str[:10], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue

    return datetime.now().strftime("%Y-%m-%d")


def fetch_url(url: str, timeout: int = 10) -> Optional[bytes]:
    """Fetches URL content with timeout and desktop User-Agent."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read()
            else:
                logger.warning(f"HTTP {resp.status} for {url}")
                return None
    except urllib.error.HTTPError as e:
        logger.warning(f"HTTP {e.code} ({e.reason}) for {url}")
        return None
    except urllib.error.URLError as e:
        logger.warning(f"Connection/Timeout Error ({e.reason}) for {url}")
        return None
    except TimeoutError:
        logger.warning(f"Timeout (exceeded {timeout}s) for {url}")
        return None
    except Exception as e:
        logger.warning(f"Fetch failed for {url}: {e}")
        return None


def parse_rss_feed(content: bytes, source_name: str, default_category: str) -> List[Dict[str, Any]]:
    """Parses RSS or Atom XML feed content."""
    items_data = []
    try:
        root = ET.fromstring(content)
    except Exception as e:
        logger.warning(f"XML parse error for {source_name}: {e}")
        return []

    # Check RSS 2.0 items
    items = root.findall(".//item")
    if items:
        for it in items:
            title = clean_html_text(it.findtext("title"))
            link = clean_html_text(it.findtext("link"))
            if not link:
                guid = it.find("guid")
                if guid is not None and guid.text and guid.text.startswith("http"):
                    link = guid.text.strip()
            pub_date = parse_date(it.findtext("pubDate"))
            description = clean_html_text(it.findtext("description"))

            if title:
                items_data.append({
                    "title": title,
                    "link": link,
                    "date": pub_date,
                    "summary": description,
                    "content": description,
                    "source_name": source_name,
                    "default_category": default_category
                })
        return items_data

    # Check Atom entries
    entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
    for en in entries:
        title = clean_html_text(en.findtext("{http://www.w3.org/2005/Atom}title") or en.findtext("title"))
        link_elem = en.find("{http://www.w3.org/2005/Atom}link")
        if link_elem is None:
            link_elem = en.find("link")
        link = ""
        if link_elem is not None:
            link = link_elem.get("href") or link_elem.text or ""
        pub_date = parse_date(
            en.findtext("{http://www.w3.org/2005/Atom}published") or
            en.findtext("{http://www.w3.org/2005/Atom}updated") or
            en.findtext("published") or
            en.findtext("updated")
        )
        summary = clean_html_text(
            en.findtext("{http://www.w3.org/2005/Atom}summary") or
            en.findtext("{http://www.w3.org/2005/Atom}content") or
            en.findtext("summary") or
            en.findtext("content")
        )
        if title:
            items_data.append({
                "title": title,
                "link": link,
                "date": pub_date,
                "summary": summary,
                "content": summary,
                "source_name": source_name,
                "default_category": default_category
            })

    return items_data


def tag_item(item: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Matches keywords, detects competitors, and confirms category."""
    title = item["title"]
    summary = item.get("summary", "")
    full_text = f"{title} {summary}"

    competitors = profile.get("competitors", [])
    interest_keywords = profile.get("interest_keywords", [])
    funding_keywords = profile.get("funding_keywords", [])

    matched_keywords = []
    matched_competitors = []

    for kw in interest_keywords:
        if kw.lower() in full_text.lower():
            matched_keywords.append(kw)

    for fkw in funding_keywords:
        if fkw.lower() in full_text.lower():
            matched_keywords.append(fkw)

    for comp in competitors:
        if comp.lower() in full_text.lower():
            matched_competitors.append(comp)

    # Determine category
    category = item.get("default_category", "market")
    if matched_competitors:
        category = "competitor"
    elif any(fkw.lower() in full_text.lower() for fkw in funding_keywords) or category == "policy":
        category = "policy"
    elif "ai" in full_text.lower() or "비전" in full_text or "기술" in full_text or category == "tech":
        category = "tech"

    company_tag = "|".join(matched_competitors) if matched_competitors else ""
    keywords_str = "|".join(dict.fromkeys(matched_keywords))  # unique preserving order

    return {
        "category": category,
        "company_tag": company_tag,
        "keywords": keywords_str
    }


def build_google_news_rss_url(query: str) -> str:
    """Builds Google News RSS URL with Korean locale."""
    encoded_query = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"


def crawl_live_sources(profile: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Crawls all planned public sources and returns collected items and failed sources."""
    sources = []

    # 1. Google News RSS for interest keywords
    for kw in profile.get("interest_keywords", ["스마트팩토리", "AI 품질검사", "제조 AX"]):
        sources.append({
            "name": f"Google News ({kw})",
            "url": build_google_news_rss_url(kw),
            "category": "market"
        })

    # 2. Google News RSS for funding keywords
    for fkw in profile.get("funding_keywords", ["AI 바우처", "스마트공장", "창업지원"]):
        sources.append({
            "name": f"Google News ({fkw})",
            "url": build_google_news_rss_url(fkw),
            "category": "policy"
        })

    # 3. Google News RSS for competitors
    for comp in profile.get("competitors", ["VisionForge", "InspectAI", "FactoryMind"]):
        sources.append({
            "name": f"Google News ({comp})",
            "url": build_google_news_rss_url(comp),
            "category": "competitor"
        })

    # 4. Specialized media RSS
    sources.append({
        "name": "AI Times",
        "url": "https://www.aitimes.com/rss/allArticle.xml",
        "category": "tech"
    })
    sources.append({
        "name": "대한민국 정책브리핑 (경제/산업)",
        "url": "https://www.korea.kr/rss/economy.xml",
        "category": "policy"
    })
    sources.append({
        "name": "전자신문 IT/산업",
        "url": "https://rss.etnews.com/Section902.xml",
        "category": "market"
    })
    sources.append({
        "name": "ZDNet Korea",
        "url": "http://feeds.feedburner.com/zdkorea",
        "category": "tech"
    })
    sources.append({
        "name": "GeekNews",
        "url": "https://news.hada.io/rss/news",
        "category": "tech"
    })

    collected_raw = []
    failed_sources = []
    seen_urls = set()

    kst = timezone(timedelta(hours=9))
    collected_at_str = datetime.now(kst).isoformat(timespec="seconds")

    logger.info(f"Starting crawl for {len(sources)} sources...")

    for src in sources:
        src_name = src["name"]
        url = src["url"]
        cat = src["category"]
        try:
            content = fetch_url(url, timeout=8)
            if not content:
                failed_sources.append(src_name)
                logger.warning(f"[FAIL] {src_name} returned no content")
                continue

            items = parse_rss_feed(content, src_name, cat)
            if not items:
                failed_sources.append(src_name)
                logger.warning(f"[FAIL] {src_name} parsed 0 items")
                continue

            added_count = 0
            for item in items:
                link = item["link"]
                # Deduplicate by link or title
                dedup_key = link if link else item["title"]
                if dedup_key in seen_urls:
                    continue
                seen_urls.add(dedup_key)

                tags = tag_item(item, profile)
                collected_raw.append({
                    "category": tags["category"],
                    "title": item["title"],
                    "date": item["date"],
                    "content": item["content"],
                    "summary": item["summary"],
                    "source_url": item["link"],
                    "source_name": item["source_name"],
                    "company_tag": tags["company_tag"],
                    "keywords": tags["keywords"],
                    "collected_at": collected_at_str,
                    "has_null": "false" if (item["title"] and item["summary"]) else "true",
                    "is_duplicate_seed": "false",
                    "data_origin": "live"
                })
                added_count += 1

            logger.info(f"[SUCCESS] {src_name}: fetched {len(items)} items, added {added_count} unique items")

        except Exception as e:
            failed_sources.append(src_name)
            logger.error(f"[ERROR] Exception crawling {src_name}: {e}")

    logger.info(f"Live crawl completed. Total unique items: {len(collected_raw)}. Failed sources: {len(failed_sources)}")
    return collected_raw, failed_sources


def crawl_backup_sources(profile: Dict[str, Any], seen_urls: set) -> List[Dict[str, Any]]:
    """Alternative sources tried if initial live count is below target."""
    backup_queries = ["머신비전", "비전 AI", "공장 자동화", "제조 AI 솔루션", "중소기업 스마트제조"]
    backup_items = []
    kst = timezone(timedelta(hours=9))
    collected_at_str = datetime.now(kst).isoformat(timespec="seconds")

    logger.info("Executing backup sources...")
    for q in backup_queries:
        src_name = f"Google News Backup ({q})"
        url = build_google_news_rss_url(q)
        content = fetch_url(url, timeout=8)
        if not content:
            continue
        items = parse_rss_feed(content, src_name, "market")
        for item in items:
            dedup_key = item["link"] if item["link"] else item["title"]
            if dedup_key in seen_urls:
                continue
            seen_urls.add(dedup_key)
            tags = tag_item(item, profile)
            backup_items.append({
                "category": tags["category"],
                "title": item["title"],
                "date": item["date"],
                "content": item["content"],
                "summary": item["summary"],
                "source_url": item["link"],
                "source_name": item["source_name"],
                "company_tag": tags["company_tag"],
                "keywords": tags["keywords"],
                "collected_at": collected_at_str,
                "has_null": "false" if (item["title"] and item["summary"]) else "true",
                "is_duplicate_seed": "false",
                "data_origin": "live"
            })
    return backup_items


def load_fallback_data(needed_count: int) -> List[Dict[str, Any]]:
    """Loads records from fallback CSV when live data is insufficient."""
    fallback_records = []
    if not os.path.exists(FALLBACK_DATA_PATH):
        logger.error(f"Fallback file not found at {FALLBACK_DATA_PATH}")
        return []

    try:
        with open(FALLBACK_DATA_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalize keys
                rec = {
                    "category": row.get("category", "market"),
                    "title": row.get("title", ""),
                    "date": row.get("date", datetime.now().strftime("%Y-%m-%d")),
                    "content": row.get("content", ""),
                    "summary": row.get("summary", ""),
                    "source_url": row.get("source_url", ""),
                    "source_name": row.get("source_name", "Fallback Source"),
                    "company_tag": row.get("company_tag", ""),
                    "keywords": row.get("keywords", ""),
                    "collected_at": row.get("collected_at", datetime.now().isoformat()),
                    "has_null": row.get("has_null", "false"),
                    "is_duplicate_seed": row.get("is_duplicate_seed", "false"),
                    "data_origin": "synthetic_fallback"
                }
                fallback_records.append(rec)
                if len(fallback_records) >= needed_count:
                    break
        logger.info(f"Loaded {len(fallback_records)} records from fallback CSV")
    except Exception as e:
        logger.error(f"Failed to load fallback CSV: {e}")

    return fallback_records


def run_crawler() -> Tuple[str, Dict[str, Any]]:
    """Executes crawler pipeline and returns (status, stats)."""
    logger.info("=== Starting Market News Crawler ===")
    profile = load_company_profile(CONFIG_PATH)

    # 1. Live Crawling
    live_items, failed_sources = crawl_live_sources(profile)

    # 2. Check if under 200 items, attempt backup sources
    seen_urls = {item["source_url"] for item in live_items}
    if len(live_items) < 200:
        logger.warning(f"Live items ({len(live_items)}) < 200. Attempting backup queries...")
        backup_items = crawl_backup_sources(profile, seen_urls)
        live_items.extend(backup_items)
        logger.info(f"Live items after backup queries: {len(live_items)}")

    # 3. Check if still under 200 items, merge fallback data
    target_count = 200
    fallback_used_count = 0
    final_items = list(live_items)

    if len(final_items) < target_count:
        needed = target_count - len(final_items)
        logger.warning(f"Total live items ({len(final_items)}) < {target_count}. Merging {needed} fallback items...")
        fallback_items = load_fallback_data(needed)
        final_items.extend(fallback_items)
        fallback_used_count = len(fallback_items)

    # 4. Assign article_id
    fieldnames = [
        "article_id", "category", "title", "date", "content", "summary",
        "source_url", "source_name", "company_tag", "keywords",
        "collected_at", "has_null", "is_duplicate_seed", "data_origin"
    ]

    for idx, item in enumerate(final_items, start=1):
        if item["data_origin"] == "live":
            item["article_id"] = f"LIVE-{idx:04d}"
        else:
            item["article_id"] = f"FB-{idx:04d}"

    # 5. Save to data/raw/crawled_market_news.csv
    try:
        with open(RAW_DATA_PATH, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for it in final_items:
                row = {k: it.get(k, "") for k in fieldnames}
                writer.writerow(row)
        logger.info(f"Successfully saved {len(final_items)} records to {RAW_DATA_PATH}")
    except Exception as e:
        logger.error(f"Failed to write CSV: {e}")
        return "FAILED", {"total": 0, "live": 0, "fallback": 0, "error": str(e)}

    live_count = sum(1 for it in final_items if it["data_origin"] == "live")
    fb_count = sum(1 for it in final_items if it["data_origin"] == "synthetic_fallback")

    status = "SUCCESS"
    if fb_count > 0:
        status = "WARNING"
    elif not final_items:
        status = "FAILED"

    stats = {
        "total": len(final_items),
        "live": live_count,
        "fallback": fb_count,
        "failed_sources": failed_sources,
        "output_file": RAW_DATA_PATH
    }
    return status, stats


def main() -> None:
    """Main execution orchestrating crawling, fallback check, and saving."""
    status, stats = run_crawler()
    print("\n" + "=" * 50)
    print("CRAWLER EXECUTION SUMMARY")
    print("=" * 50)
    print(f"Status              : {status}")
    print(f"Total Records Saved : {stats.get('total', 0)}")
    print(f"Live Records        : {stats.get('live', 0)}")
    print(f"Fallback Records    : {stats.get('fallback', 0)}")
    print(f"Failed Sources ({len(stats.get('failed_sources', []))}) : {', '.join(stats.get('failed_sources', [])) if stats.get('failed_sources') else 'None'}")
    print(f"Output File         : {stats.get('output_file')}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
