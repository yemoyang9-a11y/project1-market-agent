"""Market News Recommender for NovaFactory AI.

Evaluates market news based on keyword matching, company relevance,
competitor monitoring, and funding/policy importance.
Supports LLM evaluation (Gemini) if API key is provided,
or seamlessly falls back to a sophisticated rule-based engine.
Outputs top 30 recommendations to data/processed/recommended_market_news.csv.
"""

import os
import sys
import re
import csv
import json
import logging
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple, Optional

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "company_profile.yaml")
RAW_DATA_PATH = os.path.join(BASE_DIR, "data", "raw", "crawled_market_news.csv")
FALLBACK_DATA_PATH = os.path.join(BASE_DIR, "data", "fallback", "fallback_market_news.csv")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
CLEANED_DATA_PATH = os.path.join(PROCESSED_DIR, "cleaned_market_news.csv")
RECOMMENDED_DATA_PATH = os.path.join(PROCESSED_DIR, "recommended_market_news.csv")
LOG_PATH = os.path.join(BASE_DIR, "logs", "recommender.log")

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
logger = logging.getLogger("recommender")


def load_env() -> Dict[str, str]:
    """Loads environment variables from .env file without external dependencies."""
    env = dict(os.environ)
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                if k and v:
                    env[k] = v
    return env


def load_company_profile() -> Dict[str, Any]:
    """Loads company profile configuration."""
    try:
        import yaml
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load yaml config: {e}")

    return {
        "company_name": "NovaFactory AI",
        "business_area": "제조업 AI 비전 품질검사",
        "products": ["비전 기반 불량 탐지 SaaS", "제조 품질 리포트 자동화"],
        "target_market": ["중소·중견 제조기업", "스마트팩토리 구축 기업"],
        "competitors": ["VisionForge", "InspectAI", "FactoryMind", "QualiBot"],
        "interest_keywords": ["AI", "스마트팩토리", "품질검사", "자동화", "클라우드", "제조 AX"],
        "funding_keywords": ["창업지원", "AI 바우처", "스마트공장", "R&D", "사업화 자금"]
    }


def clean_raw_data() -> List[Dict[str, Any]]:
    """Loads raw or fallback data, removes duplicates and nulls, and saves cleaned_market_news.csv."""
    source_path = RAW_DATA_PATH if os.path.exists(RAW_DATA_PATH) else FALLBACK_DATA_PATH
    if not os.path.exists(source_path):
        logger.error(f"Neither raw data nor fallback data found at {RAW_DATA_PATH} or {FALLBACK_DATA_PATH}")
        return []

    logger.info(f"Loading data from {source_path} for cleaning...")
    cleaned_rows = []
    seen_titles = set()
    seen_urls = set()

    with open(source_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            title = (row.get("title") or "").strip()
            url = (row.get("source_url") or "").strip()
            summary = (row.get("summary") or "").strip()

            # Skip empty titles or invalid records
            if not title or len(title) < 4:
                continue

            # Deduplication key
            norm_title = re.sub(r"\s+", "", title).lower()
            if norm_title in seen_titles:
                continue
            if url and url in seen_urls:
                continue

            seen_titles.add(norm_title)
            if url:
                seen_urls.add(url)

            # Standardize date
            date = (row.get("date") or "").strip()
            if not date or len(date) < 10:
                date = datetime.now().strftime("%Y-%m-%d")

            row_cleaned = dict(row)
            row_cleaned["title"] = title
            row_cleaned["date"] = date[:10]
            row_cleaned["summary"] = summary
            row_cleaned["has_null"] = "false" if (title and summary) else "true"
            cleaned_rows.append(row_cleaned)

    logger.info(f"Cleaned {len(cleaned_rows)} unique records. Saving to {CLEANED_DATA_PATH}...")
    fieldnames = list(cleaned_rows[0].keys()) if cleaned_rows else [
        "article_id", "category", "title", "date", "content", "summary",
        "source_url", "source_name", "company_tag", "keywords",
        "collected_at", "has_null", "is_duplicate_seed", "data_origin"
    ]

    with open(CLEANED_DATA_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    return cleaned_rows


def calculate_rule_score(item: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Calculates multi-dimensional relevance score (0-100) and rule-based evaluation details."""
    title = item.get("title", "")
    summary = item.get("summary", "")
    text = f"{title} {summary}".lower()

    competitors = [c.lower() for c in profile.get("competitors", [])]
    interest_keywords = [k.lower() for k in profile.get("interest_keywords", [])]
    funding_keywords = [k.lower() for k in profile.get("funding_keywords", [])]

    # Domain specific weights
    core_vision_keywords = ["품질검사", "비전", "불량", "검출", "머신비전", "vision", "defect", "inspection"]
    manufacturing_keywords = ["스마트팩토리", "스마트공장", "제조 ax", "제조업", "생산", "공장"]

    score_keyword = 0.0
    matched_interests = [kw for kw in interest_keywords if kw in text]
    score_keyword += min(len(matched_interests) * 8.0, 25.0)

    score_company = 0.0
    matched_vision = [kw for kw in core_vision_keywords if kw in text]
    matched_mfg = [kw for kw in manufacturing_keywords if kw in text]
    score_company += min(len(matched_vision) * 12.0, 25.0)
    score_company += min(len(matched_mfg) * 6.0, 15.0)

    score_competitor = 0.0
    matched_comp = [c for c in competitors if c in text]
    if matched_comp:
        score_competitor = 25.0
    elif item.get("category") == "competitor":
        score_competitor = 15.0

    score_funding = 0.0
    matched_funding = [kw for kw in funding_keywords if kw in text]
    if matched_funding:
        score_funding += min(len(matched_funding) * 10.0, 20.0)

    # Recency bonus (within last 30 days)
    recency_bonus = 5.0
    try:
        art_date = datetime.strptime(item.get("date", "")[:10], "%Y-%m-%d")
        days_diff = (datetime.now() - art_date).days
        if days_diff <= 14:
            recency_bonus = 10.0
        elif days_diff <= 30:
            recency_bonus = 7.0
        elif days_diff > 180:
            recency_bonus = 2.0
    except Exception:
        pass

    raw_total = score_keyword + score_company + score_competitor + score_funding + recency_bonus
    total_score = round(min(max(raw_total, 10.0), 99.0), 1)

    # Corporate relevance, business importance, action necessity
    # Scale 1-5
    corp_relevance = 3
    if matched_vision:
        corp_relevance = 5
    elif matched_interests or matched_mfg:
        corp_relevance = 4

    biz_importance = 3
    if matched_funding or "바우처" in text or "예산" in text:
        biz_importance = 5
    elif matched_comp or score_company > 20:
        biz_importance = 4

    # Action necessity determination
    if matched_funding:
        action_necessity = "지원사업 공모 및 고객사 바우처 연계 검토"
    elif matched_comp:
        action_necessity = "경쟁 솔루션 기능/가격 벤치마킹 필요"
    elif matched_vision:
        action_necessity = "비전 AI 불량 검출 알고리즘 및 제품 로드맵 반영"
    elif "ax" in text or "스마트공장" in text:
        action_necessity = "중소제조 타깃 고객사 발굴 및 영업 파이프라인 연계"
    else:
        action_necessity = "시장 및 규제 트렌드 모니터링"

    # Generate rich recommendation reason
    reason_parts = []
    if matched_funding:
        reason_parts.append(f"정부 정책/펀딩 핵심 키워드({', '.join(matched_funding[:2])})가 포함되어 고객사 유입 기회 분석에 직결됨.")
    if matched_vision:
        reason_parts.append("NovaFactory AI의 핵심인 비전 불량 검출 기술 고도화와 직접적 연관성이 높음.")
    elif matched_mfg:
        reason_parts.append("스마트팩토리 및 제조 AX 확산 국면에서 주요 잠재 고객사 수요를 파악하기에 최적임.")
    if matched_comp:
        reason_parts.append(f"경쟁사({', '.join(matched_comp)}) 동향으로 자사 SaaS의 시장 포지셔닝 검증에 필수적임.")

    if not reason_parts:
        reason_parts.append(f"산업 자동화 및 AI 기술 동향 키워드 매칭(관련성 점수 {total_score}점)으로 시장 환경 분석에 유효함.")

    recommendation_reason = " ".join(reason_parts)

    eval_info = {
        "corporate_relevance": corp_relevance,
        "business_importance": biz_importance,
        "action_necessity": action_necessity,
        "recommendation_reason": recommendation_reason
    }

    return total_score, eval_info


def call_gemini_llm(candidates: List[Dict[str, Any]], profile: Dict[str, Any], api_key: str) -> bool:
    """Evaluates top candidates using Gemini API via urllib HTTP request if API key is provided."""
    logger.info(f"Attempting Gemini LLM evaluation for {len(candidates)} candidates...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    # Prepare prompt with batch items
    items_snippet = []
    for idx, c in enumerate(candidates, 1):
        items_snippet.append({
            "index": idx,
            "title": c.get("title", ""),
            "summary": c.get("summary", "")[:200],
            "category": c.get("category", "")
        })

    prompt_text = f"""
당신은 'NovaFactory AI'(제조업 AI 비전 품질검사 SaaS 전문 기업)의 비즈니스 인텔리전스 전략가입니다.
아래 뉴스 목록을 분석하여 각 기사의 기업 관련성(1~5), 사업 중요도(1~5), 대응 필요성(한 문장), 추천 이유(1~2문장)를 JSON 배열로 평가해 주세요.

목표 시장: 중소·중견 제조기업, 스마트팩토리 구축 기업
주요 제품: 비전 기반 불량 탐지 SaaS, 제조 품질 리포트 자동화

뉴스 목록:
{json.dumps(items_snippet, ensure_ascii=False, indent=2)}

반드시 아래 JSON 형식의 배열로만 반환하세요:
[
  {{
    "index": 1,
    "corporate_relevance": 5,
    "business_importance": 4,
    "action_necessity": "대응 필요성 한 문장",
    "recommendation_reason": "추천 이유 1~2문장"
  }}
]
"""
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                resp_data = json.loads(resp.read().decode("utf-8"))
                text_out = resp_data["candidates"][0]["content"]["parts"][0]["text"]
                results = json.loads(text_out)
                results_map = {r.get("index"): r for r in results if isinstance(r, dict)}

                for idx, c in enumerate(candidates, 1):
                    res = results_map.get(idx)
                    if res:
                        c["corporate_relevance"] = res.get("corporate_relevance", c.get("corporate_relevance", 4))
                        c["business_importance"] = res.get("business_importance", c.get("business_importance", 4))
                        c["action_necessity"] = res.get("action_necessity", c.get("action_necessity", ""))
                        c["recommendation_reason"] = res.get("recommendation_reason", c.get("recommendation_reason", ""))
                logger.info("Successfully updated recommendations with Gemini LLM insights!")
                return True
    except Exception as e:
        logger.warning(f"Gemini LLM evaluation failed: {e}. Keeping rule-based evaluations.")

    return False


def recommend_news(top_n: int = 30) -> Tuple[List[Dict[str, Any]], bool]:
    """Orchestrates cleaning, scoring, LLM/rule evaluation, and saves top 30 recommendations."""
    env = load_env()
    profile = load_company_profile()

    # 1. Clean or load data
    if os.path.exists(CLEANED_DATA_PATH):
        logger.info(f"Loading existing cleaned data from {CLEANED_DATA_PATH}...")
        records = []
        with open(CLEANED_DATA_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            records = list(reader)
        if not records:
            records = clean_raw_data()
    else:
        records = clean_raw_data()

    if not records:
        logger.error("No data available for recommendation.")
        return [], False

    logger.info(f"Scoring {len(records)} records for {profile.get('company_name', 'NovaFactory AI')}...")

    # 2. Rule-based scoring
    scored_records = []
    for item in records:
        score, eval_info = calculate_rule_score(item, profile)
        item_copy = dict(item)
        item_copy["total_score"] = score
        item_copy["corporate_relevance"] = eval_info["corporate_relevance"]
        item_copy["business_importance"] = eval_info["business_importance"]
        item_copy["action_necessity"] = eval_info["action_necessity"]
        item_copy["recommendation_reason"] = eval_info["recommendation_reason"]
        scored_records.append(item_copy)

    # Sort descending by score
    scored_records.sort(key=lambda x: x["total_score"], reverse=True)

    # 3. Select top N candidates
    top_candidates = scored_records[:top_n]

    # 4. Optional Gemini LLM evaluation
    api_key = env.get("GEMINI_API_KEY", "").strip()
    enable_llm = env.get("ENABLE_LLM_RELEVANCE", "true").lower() != "false"
    llm_used = False

    if api_key and enable_llm:
        llm_used = call_gemini_llm(top_candidates, profile, api_key)
    else:
        logger.info("No Gemini API Key provided (or ENABLE_LLM_RELEVANCE=false). Proceeding with robust rule-based engine.")

    # 5. Format and save to recommended_market_news.csv
    fieldnames = [
        "rank", "article_id", "category", "title", "date", "total_score",
        "corporate_relevance", "business_importance", "action_necessity",
        "recommendation_reason", "source_url", "source_name", "keywords",
        "company_tag", "data_origin"
    ]

    for rank, item in enumerate(top_candidates, 1):
        item["rank"] = rank

    with open(RECOMMENDED_DATA_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in top_candidates:
            row = {k: item.get(k, "") for k in fieldnames}
            writer.writerow(row)

    logger.info(f"Saved {len(top_candidates)} recommendations to {RECOMMENDED_DATA_PATH}")

    return top_candidates, llm_used


def run_recommender(top_n: int = 30) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """Runs recommendation process and returns (status, items, stats)."""
    top_items, llm_used = recommend_news(top_n=top_n)
    if not top_items:
        return "FAILED", [], {"count": 0, "llm_used": llm_used}
    status = "SUCCESS" if len(top_items) >= top_n else "WARNING"
    return status, top_items, {"count": len(top_items), "llm_used": llm_used}


def main() -> None:
    """Command line entrypoint."""
    top_items, llm_used = recommend_news(top_n=30)
    print("\n" + "=" * 60)
    print("RECOMMENDATION SUMMARY (TOP 10)")
    print("=" * 60)
    print(f"LLM Evaluator Status: {'Gemini API Enabled' if llm_used else 'Rule-Based Engine Active'}")
    print(f"Total Recommended: {len(top_items)} items saved to {RECOMMENDED_DATA_PATH}\n")

    for item in top_items[:10]:
        print(f"[{item['rank']:02d}] Score: {item['total_score']} | [{item['category']}] {item['title'][:45]}")
        print(f"     Reason: {item['recommendation_reason'][:70]}...")
        print(f"     URL   : {item['source_url']}")
        print("-" * 60)


if __name__ == "__main__":
    main()
