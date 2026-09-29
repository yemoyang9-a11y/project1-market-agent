# project1-market-agent

> **NovaFactory AI**를 위한 시장 동향 및 경쟁사 정보 자동 수집·분석 에이전트

본 프로젝트는 제조업 AI 비전 품질검사 분야의 시장 트렌드, 경쟁사 동향, 정부 지원사업/펀딩 정보를 자동으로 수집 및 정제하고, 분석 리포트를 생성하여 GitHub Pages로 배포하는 파이프라인입니다.

---

## 1. 프로젝트 디렉터리 구조

```text
project1-market-agent/
├── .github/
│   └── workflows/          # GitHub Actions 자동화 워크플로우
├── config/
│   └── company_profile.yaml# 기업 프로필, 경쟁사 및 수집 키워드 설정
├── data/
│   ├── fallback/           # 네트워크 실패 대비 합성 fallback 데이터 (800행)
│   │   └── fallback_market_news.csv
│   ├── raw/                # 수집된 원시 데이터 (.gitkeep)
│   └── processed/          # 중복 제거 및 필터링 완료 데이터 (.gitkeep)
├── docs/                   # GitHub Pages 배포용 웹 문서 및 대시보드
│   └── index.md
├── logs/                   # 실행 로그 저장소 (.gitkeep)
├── src/                    # 에이전트 핵심 소스코드
│   └── __init__.py
├── .env.example            # 환경변수 템플릿
├── .gitignore              # Git 제외 파일 목록
├── requirements.txt        # Python 의존성 목록
└── README.md               # 프로젝트 안내 문서
```

---

## 2. 기업 프로필 및 수집 기준 (`config/company_profile.yaml`)

* **기업명 (`company_name`):** NovaFactory AI
* **사업 분야 (`business_area`):** 제조업 AI 비전 품질검사
* **주요 제품 (`products`):**
  - 비전 기반 불량 탐지 SaaS
  - 제조 품질 리포트 자동화
* **목표 시장 (`target_market`):**
  - 중소·중견 제조기업
  - 스마트팩토리 구축 기업
* **주요 경쟁사 (`competitors` - 4개):**
  - `VisionForge`, `InspectAI`, `FactoryMind`, `QualiBot`
* **관심 키워드 (`interest_keywords` - 6개):**
  - `AI`, `스마트팩토리`, `품질검사`, `자동화`, `클라우드`, `제조 AX`
* **지원사업/펀딩 키워드 (`funding_keywords` - 5개):**
  - `창업지원`, `AI 바우처`, `스마트공장`, `R&D`, `사업화 자금`

---

## 3. 데이터 정책 (Data Policy)

1. **실시간 수집 우선:** 공개 웹 검색, RSS 피드 크롤링을 1차로 시도합니다.
2. **Fallback 보장:** 네트워크 제한, Rate-limit, 수집량 부족 시 `data/fallback/fallback_market_news.csv` (800행 합성 데이터)를 활용하여 파이프라인의 무중단 안정성을 보장합니다.

---

## 4. 환경 설정 및 실행 방법

### 가상환경 구성 및 패키지 설치
```bash
# 가상환경 생성
python -m venv .venv

# 가상환경 활성화 (Windows PowerShell)
.venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt
```

### 환경변수 설정
```bash
cp .env.example .env
# .env 파일 내 GEMINI_API_KEY 등 필요 키 입력
```
