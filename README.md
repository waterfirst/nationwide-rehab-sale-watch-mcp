# 리세일 레이더

전국 6개 회생법원의 공개 자산 매각 공고를 누적 수집하고, 사용자가 확인한 당근·번개장터·중고나라 비교 시세를 근거로 **최대 입찰가, 권장 판매가, 예상 이익**을 계산하는 MCP + 웹 대시보드입니다.

> 공개 공고와 입력한 시세를 이용하는 의사결정 보조 도구입니다. 법률·세무·투자 자문이나 수익 보장을 제공하지 않습니다.

## 이번 버전의 핵심

- 세련된 반응형 React 사업 대시보드
- SQLite 기반 공고·관측·시세·평가·실행 이력 누적
- 현재 페이지 스냅샷이 아닌 전체 이력 기준 신규 감지
- 한 법원 장애가 전국 수집을 멈추지 않는 소스별 장애 격리
- 법원별 마지막 성공 시각, 응답 속도, 감지 건수, 연속 실패 표시
- 전자제품·Apple·귀금속·시계·비품·설비·부동산 분류
- 시세 중앙값과 비용·위험·목표 마진을 반영한 보수적 입찰가 산정
- 외부 URL을 악용한 SSRF 방지: 지원 법원 HTTPS 주소만 상세 조회
- Linux, Windows, 다른 설치 경로에서도 동작하는 환경 독립 데이터 경로

## 화면에서 하는 일

1. **지금 수집**으로 서울·수원·부산·대구·대전·광주 회생법원 공고를 확인합니다.
2. 우선 검토 후보를 선택합니다.
3. 당근·번개장터·중고나라에서 같은 모델·상태의 판매 희망가를 확인해 근거를 입력합니다.
4. 최소 3건을 권장하며, 계산 버튼으로 최대 입찰가와 권장 판매가를 갱신합니다.
5. 법원 원문, 실물 상태, 권리, 세금, 운송·수리 비용을 확인한 뒤 입찰 여부를 결정합니다.

중고 플랫폼을 무단 자동 수집하지 않습니다. 시세는 사용자가 확인한 링크와 가격만 저장하도록 설계했습니다. 향후 공식 API 또는 제휴 데이터 사용 권한이 확보되면 `comparables` 입력 계층을 공급자 어댑터로 확장할 수 있습니다.

## 빠른 실행

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd web
npm install
npm run build
cd ..

python run_web.py
```

브라우저에서 `http://127.0.0.1:8010`을 엽니다.

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Set-Location web
npm install
npm run build
Set-Location ..

python run_web.py
```

## 개발 모드

터미널 1:

```bash
.venv/bin/uvicorn nationwide_rehab_sale_watch_mcp.api:app --host 127.0.0.1 --port 8010
```

터미널 2:

```bash
cd web
npm run dev
```

React 개발 화면은 `http://127.0.0.1:5173`이며 `/api` 요청을 Python 서버로 전달합니다.

## 최대 입찰가 계산

입력 시세의 IQR 이상치를 제거한 중앙값을 기준으로 계산합니다.

```text
권장 판매가 = 시세 중앙값 × 상태 보정
예상 체결가 = 권장 판매가 × 협상 체결률
최대 입찰가 = (예상 체결가 - 판매수수료 - 수리비 - 물류비
              - 위험 버퍼 - 목표 이익) ÷ (1 + 취득 부대비율)
```

기본 가정:

| 항목 | 기본값 | 의미 |
|---|---:|---|
| 상태 보정 | 92% | 법원 물품의 검수·보증 한계 반영 |
| 협상 체결률 | 96% | 게시가 대비 실제 협상 할인 |
| 판매 수수료 | 4% | 결제·플랫폼 비용 가정 |
| 취득 부대비 | 2% | 입찰·인수 부대비 가정 |
| 수리비 | 5만원 | 점검·소모품·세척 비용 |
| 물류비 | 3만원 | 포장·운송 비용 |
| 위험 버퍼 | 10% | 미확인 하자·반품·회전 위험 |
| 목표 마진 | 18% | 예상 체결가 기준 목표 이익 |

품목과 입찰 조건에 맞게 가정을 조정해야 합니다. 특히 귀금속, 부동산, 자동차, 대형 설비는 별도 감정·세금·운송 모델이 필요합니다.

## MCP 도구

- `list_courts()` — 지원 법원과 공식 URL
- `list_sale_notices(...)` — 최신 공고 통합 조회, 부분 장애 결과 포함
- `get_sale_notice_detail(...)` — 공식 법원 상세 공고 조회
- `list_new_sale_notices(...)` — SQLite 전체 이력 대비 신규 공고
- `scan_sale_candidates(...)` — 관심 품목 후보 선별 및 누적 저장
- `get_watch_dashboard(...)` — 누적 공고·수집 상태·실행 이력 요약
- `recommend_bid_price(...)` — 입력 시세 기반 최대 입찰가·판매가 산정

MCP 실행:

```bash
python -m nationwide_rehab_sale_watch_mcp.server
```

## 웹 API

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | `/api/health` | DB 및 소스 상태 |
| GET | `/api/dashboard` | KPI, 후보, 법원 상태, 실행 이력 |
| POST | `/api/scans` | 전국 또는 선택 법원 수집 |
| GET | `/api/listings` | 검색·우선순위·법원 필터 |
| GET | `/api/listings/{id}` | 공고·시세·최근 평가 상세 |
| POST | `/api/listings/{id}/comparables` | 검증한 중고 시세 근거 추가 |
| POST | `/api/listings/{id}/valuation` | 저장 시세로 평가 생성 |
| POST | `/api/valuations/preview` | 임의 시세 목록 평가 미리보기 |

## 데이터 구조

기본 DB는 `records/rehab_watch.db`에 생성되며 Git에는 포함되지 않습니다.

- `listings`: 공고의 현재 상태와 최초/마지막 감지 시각
- `listing_observations`: 조회수·제목 관측 이력
- `scan_runs`: 실행 성공·부분 성공·실패와 신규 건수
- `source_health`: 법원별 마지막 성공·오류·지연
- `comparables`: 확인한 중고 플랫폼 시세 근거
- `valuations`: 가정과 평가 결과의 버전 이력

운영 서버에서 경로를 바꾸려면:

```bash
export REHAB_WATCH_DB_PATH=/var/lib/rehab-watch/rehab_watch.db
export REHAB_WATCH_HOST=0.0.0.0
export REHAB_WATCH_PORT=8010
```

## 자동화 권장

웹 API의 `POST /api/scans`를 cron, systemd timer 또는 사내 스케줄러에서 호출합니다. 짧은 주기의 과도한 요청은 피하고, 법원 공개 서비스의 이용정책과 서버 부하를 존중하세요.

권장 시작점:

- 평일 오전 09:14: 전국 2페이지 수집
- 오후 16:30: 신규 공고 재확인
- 연속 실패 2회 이상: 운영자 확인
- 시세 3건 미만: 입찰가를 확정하지 않고 “근거 보강” 유지

## 검증

```bash
pip install -r requirements-dev.txt
pytest -q

cd web
npm run build
```

운영 문서:

- [법원 연결 규칙](COURT_CONNECTION_RULES.md)
- [루프·종료 정책](LOOP_ORCHESTRATION_POLICY.md)
