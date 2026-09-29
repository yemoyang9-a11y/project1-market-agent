"""Static Site & Report Generator for NovaFactory AI Market Intelligence.

Builds docs/report.json and docs/index.html for GitHub Pages deployment.
Includes TOP 10 highlights, category statistics, recommendation rationale,
and direct source links.
"""

import os
import sys
import csv
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple
from collections import Counter

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
RECOMMENDED_CSV = os.path.join(PROCESSED_DIR, "recommended_market_news.csv")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
REPORT_JSON = os.path.join(DOCS_DIR, "report.json")
INDEX_HTML = os.path.join(DOCS_DIR, "index.html")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "company_profile.yaml")

os.makedirs(DOCS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("build_site")


def load_recommendations() -> List[Dict[str, Any]]:
    """Loads recommended news items from CSV."""
    if not os.path.exists(RECOMMENDED_CSV):
        logger.warning(f"{RECOMMENDED_CSV} not found. Running recommender first...")
        from recommender import recommend_news
        recommend_news(top_n=30)

    items = []
    with open(RECOMMENDED_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(dict(row))
    return items


def load_company_profile() -> Dict[str, Any]:
    """Loads profile config if available."""
    try:
        import yaml
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {
        "company_name": "NovaFactory AI",
        "business_area": "제조업 AI 비전 품질검사",
        "products": ["비전 기반 불량 탐지 SaaS", "제조 품질 리포트 자동화"],
        "target_market": ["중소·중견 제조기업", "스마트팩토리 구축 기업"]
    }


def generate_json_report(items: List[Dict[str, Any]], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Builds structured report.json file."""
    kst = timezone(timedelta(hours=9))
    now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S KST")

    cat_counts = Counter(it.get("category", "market") for it in items)
    total_count = len(items)

    category_stats = {
        cat: {
            "count": count,
            "percentage": round((count / total_count * 100), 1) if total_count else 0
        }
        for cat, count in cat_counts.items()
    }

    report_data = {
        "metadata": {
            "title": "NovaFactory AI 시장·경쟁사 인텔리전스 리포트",
            "company_name": profile.get("company_name", "NovaFactory AI"),
            "business_area": profile.get("business_area", "제조업 AI 비전 품질검사"),
            "generated_at": now_str,
            "total_recommended": total_count,
            "top_highlights_count": min(10, total_count)
        },
        "category_statistics": category_stats,
        "top_10": items[:10],
        "all_recommendations": items
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Generated {REPORT_JSON} successfully.")
    return report_data


def generate_html_dashboard(report_data: Dict[str, Any]) -> None:
    """Generates modern, responsive index.html dashboard."""
    meta = report_data["metadata"]
    stats = report_data["category_statistics"]
    top_10 = report_data["top_10"]
    all_items = report_data["all_recommendations"]

    # Category display helpers
    cat_labels = {
        "policy": "정책 / 지원사업",
        "tech": "기술 / AI 비전",
        "market": "시장 / 산업 동향",
        "competitor": "경쟁사 동향"
    }
    cat_colors = {
        "policy": "bg-purple-100 text-purple-800 border-purple-200",
        "tech": "bg-blue-100 text-blue-800 border-blue-200",
        "market": "bg-emerald-100 text-emerald-800 border-emerald-200",
        "competitor": "bg-amber-100 text-amber-800 border-amber-200"
    }

    top_cards_html = ""
    for it in top_10:
        cat = it.get("category", "market")
        cat_badge = cat_labels.get(cat, cat.upper())
        color_cls = cat_colors.get(cat, "bg-gray-100 text-gray-800 border-gray-200")
        score = it.get("total_score", "0")
        rank = int(it.get("rank", 0))

        top_cards_html += f"""
        <div class="bg-white rounded-xl shadow-sm border border-slate-200 hover:shadow-md transition-shadow p-6 relative flex flex-col justify-between">
            <div>
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center space-x-2">
                        <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold">
                            #{rank}
                        </span>
                        <span class="px-2.5 py-1 text-xs font-semibold rounded-full border {color_cls}">
                            {cat_badge}
                        </span>
                    </div>
                    <div class="text-right">
                        <span class="text-xs text-slate-400 font-medium block">관련성 점수</span>
                        <span class="text-lg font-black text-indigo-600">{score}점</span>
                    </div>
                </div>
                <h3 class="text-lg font-bold text-slate-900 leading-snug mb-2 hover:text-indigo-600 transition-colors">
                    <a href="{it.get('source_url', '#')}" target="_blank" rel="noopener noreferrer">
                        {it.get('title', '')}
                    </a>
                </h3>
                <div class="text-xs text-slate-500 mb-4 flex items-center space-x-3">
                    <span>📰 {it.get('source_name', '출처')}</span>
                    <span>•</span>
                    <span>📅 {it.get('date', '')}</span>
                </div>
                <div class="bg-indigo-50/70 border border-indigo-100 rounded-lg p-3.5 mb-4 text-xs text-slate-700 leading-relaxed">
                    <div class="font-bold text-indigo-900 mb-1 flex items-center">
                        <span class="mr-1.5">💡</span> 추천 이유 & 기업 영향
                    </div>
                    {it.get('recommendation_reason', '')}
                </div>
            </div>
            <div class="pt-3 border-t border-slate-100 flex items-center justify-between">
                <span class="text-xs font-medium text-slate-600 bg-slate-100 px-2 py-1 rounded">
                    📌 {it.get('action_necessity', '모니터링')}
                </span>
                <a href="{it.get('source_url', '#')}" target="_blank" rel="noopener noreferrer"
                   class="inline-flex items-center text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">
                    원문 보기 <span class="ml-1">→</span>
                </a>
            </div>
        </div>
        """

    # Category stats progress bars
    stats_bars_html = ""
    for cat, data in stats.items():
        label = cat_labels.get(cat, cat.upper())
        cnt = data["count"]
        pct = data["percentage"]
        stats_bars_html += f"""
        <div class="mb-4">
            <div class="flex justify-between text-xs font-semibold text-slate-700 mb-1.5">
                <span>{label} ({cnt}건)</span>
                <span>{pct}%</span>
            </div>
            <div class="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                <div class="bg-indigo-600 h-2.5 rounded-full" style="width: {pct}%"></div>
            </div>
        </div>
        """

    # Table rows for all 30
    table_rows_html = ""
    for it in all_items:
        cat = it.get("category", "market")
        cat_badge = cat_labels.get(cat, cat.upper())
        color_cls = cat_colors.get(cat, "bg-gray-100 text-gray-800 border-gray-200")
        rank = it.get("rank", "")
        table_rows_html += f"""
        <tr class="hover:bg-slate-50/80 transition-colors border-b border-slate-100 text-xs">
            <td class="py-3 px-3 font-bold text-slate-900 text-center">{rank}</td>
            <td class="py-3 px-3">
                <span class="px-2 py-0.5 rounded text-[11px] font-medium border {color_cls}">
                    {cat_badge}
                </span>
            </td>
            <td class="py-3 px-3 font-semibold text-slate-900">
                <a href="{it.get('source_url', '#')}" target="_blank" rel="noopener noreferrer" class="hover:text-indigo-600 hover:underline">
                    {it.get('title', '')}
                </a>
                <div class="text-[11px] text-slate-500 mt-1 font-normal line-clamp-1">
                    {it.get('recommendation_reason', '')}
                </div>
            </td>
            <td class="py-3 px-3 text-center font-bold text-indigo-600">{it.get('total_score', '0')}</td>
            <td class="py-3 px-3 text-slate-500 whitespace-nowrap">{it.get('source_name', '')}</td>
            <td class="py-3 px-3 text-slate-500 whitespace-nowrap text-center">{it.get('date', '')}</td>
            <td class="py-3 px-3 text-center whitespace-nowrap">
                <a href="{it.get('source_url', '#')}" target="_blank" rel="noopener noreferrer"
                   class="inline-block px-2.5 py-1 bg-slate-100 hover:bg-indigo-50 text-slate-700 hover:text-indigo-600 rounded font-medium transition-colors">
                    원문링크 ↗
                </a>
            </td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{meta['title']}</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700;800&display=swap');
        body {{
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
        }}
    </style>
</head>
<body class="bg-slate-50 text-slate-800 antialiased min-h-screen flex flex-col">

    <!-- Top Navigation Bar -->
    <header class="bg-slate-900 border-b border-slate-800 sticky top-0 z-50 text-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center font-black text-xl text-white shadow-md">
                    N
                </div>
                <div>
                    <h1 class="text-base font-bold leading-tight">{meta['company_name']}</h1>
                    <p class="text-xs text-slate-400 font-normal">Market Intelligence Dashboard</p>
                </div>
            </div>
            <div class="flex items-center space-x-4">
                <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span> 라이브 분석 완료
                </span>
                <span class="text-xs text-slate-400 hidden sm:inline">생성: {meta['generated_at']}</span>
            </div>
        </div>
    </header>

    <!-- Main Content Container -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">

        <!-- Hero Company Banner -->
        <div class="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-2xl p-8 mb-8 text-white shadow-lg relative overflow-hidden border border-slate-800">
            <div class="relative z-10 max-w-3xl">
                <div class="inline-block px-3 py-1 rounded-md bg-indigo-500/30 text-indigo-300 text-xs font-semibold mb-3 border border-indigo-400/20">
                    🎯 타깃 도메인 : {meta['business_area']}
                </div>
                <h2 class="text-2xl sm:text-3xl font-extrabold tracking-tight mb-2">
                    NovaFactory AI 맞춤형 시장·경쟁사 추천 인텔리전스
                </h2>
                <p class="text-sm text-slate-300 leading-relaxed mb-6">
                    비전 기반 불량 검사 솔루션 및 스마트팩토리 관련 공개 뉴스 1,200여 건 중 기업 관련성, 사업 중요도, 정부 지원사업 혜택 등을 종합 평가한 <strong>상위 30대 핵심 인사이트</strong>를 제공합니다.
                </p>
                <div class="flex flex-wrap gap-4 text-xs">
                    <div class="bg-white/10 backdrop-blur-sm px-3.5 py-2 rounded-lg border border-white/10">
                        <span class="text-slate-400 block">추천 엔진</span>
                        <span class="font-semibold text-white">Rule-based & AI Multi-Scoring</span>
                    </div>
                    <div class="bg-white/10 backdrop-blur-sm px-3.5 py-2 rounded-lg border border-white/10">
                        <span class="text-slate-400 block">선별 추천수</span>
                        <span class="font-semibold text-white">상위 {meta['total_recommended']}건 엄선</span>
                    </div>
                    <div class="bg-white/10 backdrop-blur-sm px-3.5 py-2 rounded-lg border border-white/10">
                        <span class="text-slate-400 block">배포 플랫폼</span>
                        <span class="font-semibold text-white">GitHub Pages 정적 대시보드</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Section 1: Top 10 Highlights Grid -->
        <div class="mb-12">
            <div class="flex items-center justify-between mb-6">
                <div>
                    <h2 class="text-xl font-black text-slate-900 flex items-center">
                        <span class="mr-2">🔥</span> TOP 10 최우선 대응 추천 뉴스
                    </h2>
                    <p class="text-xs text-slate-500 mt-1">
                        정부 지원사업 공모 기회, AI 비전 기술 혁신 및 시장 확장 동향 상위 10선
                    </p>
                </div>
                <span class="text-xs font-semibold text-indigo-600 bg-indigo-50 px-3 py-1.5 rounded-lg border border-indigo-100">
                    실시간 스코어링 순
                </span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-6">
                {top_cards_html}
            </div>
        </div>

        <!-- Section 2: Category Analytics & Distribution -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-12">
            <!-- Category Progress Card -->
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
                <h3 class="text-base font-bold text-slate-900 mb-1 flex items-center">
                    <span class="mr-2">📊</span> 카테고리별 추천 비중
                </h3>
                <p class="text-xs text-slate-500 mb-6">상위 30건의 정보 카테고리 구성</p>
                {stats_bars_html}
            </div>

            <!-- Strategy Card -->
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 lg:col-span-2 flex flex-col justify-between">
                <div>
                    <h3 class="text-base font-bold text-slate-900 mb-1 flex items-center">
                        <span class="mr-2">🎯</span> NovaFactory AI 비즈니스 대응 가이드
                    </h3>
                    <p class="text-xs text-slate-500 mb-4">현재 수집된 데이터에 기반한 에이전트 권고안</p>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-slate-700">
                        <div class="p-3.5 rounded-lg bg-purple-50/70 border border-purple-100">
                            <span class="font-bold text-purple-900 block mb-1">1. AI 바우처 & 스마트공장 자금</span>
                            중소 제조기업 고객사가 정부 바우처를 통해 NovaFactory AI 솔루션을 도입할 수 있도록 사업화 제안서 연계 추진.
                        </div>
                        <div class="p-3.5 rounded-lg bg-blue-50/70 border border-blue-100">
                            <span class="font-bold text-blue-900 block mb-1">2. 비전 품질검사 차별화</span>
                            최신 온디바이스 비전 모델 및 멀티모달 불량 판별 트렌드를 제품 로드맵에 즉시 반영하여 경쟁력 강화.
                        </div>
                        <div class="p-3.5 rounded-lg bg-emerald-50/70 border border-emerald-100">
                            <span class="font-bold text-emerald-900 block mb-1">3. 제조 AX 시장 침투</span>
                            공장 자동화 및 스마트제조 전환 수요가 급증하는 자동차 부품 및 2차전지 협력사 영업 채널 집중 공략.
                        </div>
                        <div class="p-3.5 rounded-lg bg-amber-50/70 border border-amber-100">
                            <span class="font-bold text-amber-900 block mb-1">4. 경쟁 솔루션 상시 모니터링</span>
                            경쟁사(VisionForge 등)의 신규 릴리즈 및 가격 정책을 지속 추적하여 SaaS 요금제 경쟁력 유지.
                        </div>
                    </div>
                </div>
                <div class="mt-4 pt-3 border-t border-slate-100 text-right">
                    <a href="report.json" target="_blank" class="text-xs text-indigo-600 font-semibold hover:underline">
                        JSON 원본 데이터 다운로드 (docs/report.json) →
                    </a>
                </div>
            </div>
        </div>

        <!-- Section 3: Full Recommended News Table (Top 30) -->
        <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mb-12">
            <div class="p-6 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h3 class="text-base font-bold text-slate-900 flex items-center">
                        <span class="mr-2">📋</span> 상위 30개 추천 뉴스 전체 목록
                    </h3>
                    <p class="text-xs text-slate-500 mt-1">기업 적합도 및 중요도 기준으로 정렬된 전체 추천 데이터셋</p>
                </div>
                <span class="text-xs text-slate-500 bg-slate-100 px-3 py-1 rounded-full font-medium self-start sm:self-auto">
                    총 30개 항목
                </span>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-slate-50 text-[11px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                            <th class="py-3 px-3 text-center">순위</th>
                            <th class="py-3 px-3">카테고리</th>
                            <th class="py-3 px-3">기사 제목 및 추천 이유</th>
                            <th class="py-3 px-3 text-center">점수</th>
                            <th class="py-3 px-3">출처</th>
                            <th class="py-3 px-3 text-center">발행일</th>
                            <th class="py-3 px-3 text-center">원문 링크</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {table_rows_html}
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- Footer -->
    <footer class="bg-white border-t border-slate-200 py-6 text-center text-xs text-slate-500">
        <div class="max-w-7xl mx-auto px-4">
            <p class="font-medium text-slate-700">{meta['company_name']} Market Intelligence Agent</p>
            <p class="mt-1 text-slate-400">Deployed automatically to GitHub Pages • Project 1 Pipeline</p>
        </div>
    </footer>

</body>
</html>
"""

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"Generated {INDEX_HTML} successfully.")


def run_build_site() -> Tuple[str, Dict[str, Any]]:
    """Builds static site assets and returns (status, stats)."""
    logger.info("=== Starting Static Site Build ===")
    try:
        items = load_recommendations()
        profile = load_company_profile()
        report_data = generate_json_report(items, profile)
        generate_html_dashboard(report_data)

        if not os.path.exists(INDEX_HTML) or os.path.getsize(INDEX_HTML) == 0:
            return "FAILED", {"error": "index.html generation failed"}

        stats = {
            "total_items": len(items),
            "report_json": REPORT_JSON,
            "index_html": INDEX_HTML
        }
        return "SUCCESS", stats
    except Exception as e:
        logger.error(f"Static site build failed: {e}")
        return "FAILED", {"error": str(e)}


def main() -> None:
    """Entry point for building static site assets."""
    status, stats = run_build_site()
    print("\n" + "=" * 50)
    print("STATIC SITE BUILD COMPLETE")
    print("=" * 50)
    print(f"Status     : {status}")
    print(f"Report JSON: {stats.get('report_json')}")
    print(f"Index HTML : {stats.get('index_html')}")
    print(f"Total Items: {stats.get('total_items', 0)}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
