# 전국 회생법원 매각 매물 조회 MCP

서울회생법원 전용 감시 스크립트를 전국 공통형으로 확장한 로컬 MCP 서버입니다.

공식 회생법원 공개 공고판을 읽어서 다음 용도로 사용합니다.

- 전국 회생법원 신규 매각 공고 감시
- 노트북 / Apple / 비품 / 전자기기 / 기계 / 부동산 1차 후보 선별
- 텔레그램 알림용 자동 점검
- 향후 입찰/재판매 후보 탐색용 MCP 도구

지원 법원:

- 서울회생법원 (`slb`)
- 수원회생법원 (`swb`)
- 부산회생법원 (`bsb`)
- 대구회생법원 (`dgb`)
- 대전회생법원 (`djb`)
- 광주회생법원 (`gjb`)

## 제공 도구

- `list_courts()`
  - 지원 법원 코드와 기본 URL 목록 조회
- `list_sale_notices(courts=None, limit=20, keyword=None, max_pages=2)`
  - 여러 회생법원의 최신 매각 공고를 합쳐 조회
- `get_sale_notice_detail(court=None, seq_id=None, url=None)`
  - 개별 공고 상세 조회
- `list_new_sale_notices(courts=None, limit=20, keyword=None, max_pages=2)`
  - 직전 스냅샷 대비 신규 공고만 조회하고 상태 갱신
- `scan_sale_candidates(courts=None, limit=20, interests=None, max_pages=2)`
  - 노트북/애플기기/기계/비품/부동산 등 관심 품목 중심으로 후보를 추림

## 설치

```bash
cd /home/waterfirst/.codex/mcp_servers/nationwide-rehab-sale-watch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행

```bash
python -m nationwide_rehab_sale_watch_mcp.server
```

## 빠른 테스트

### 1) 지원 법원 목록 확인

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, '.')
from nationwide_rehab_sale_watch_mcp.server import list_courts
print(list_courts())
PY
```

### 2) 서울/수원/대전 최근 공고 조회

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, '.')
from nationwide_rehab_sale_watch_mcp.server import list_sale_notices
res = list_sale_notices(courts=['slb','swb','djb'], limit=9, max_pages=1)
for item in res['items']:
    print(item['court_code'], item['title'], item['url'])
PY
```

### 3) 전국 후보 선별

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, '.')
from nationwide_rehab_sale_watch_mcp.server import scan_sale_candidates
res = scan_sale_candidates(
    courts=['slb','swb','bsb','dgb','djb','gjb'],
    interests=['notebook','apple','equipment'],
    limit=10,
    max_pages=2,
)
for item in res['items']:
    print(item['priority'], item['asset_type'], item['title'], item['matched_keywords'])
PY
```

## 운영 문서

- 연결 규칙: `COURT_CONNECTION_RULES.md`
- 루프/종료 기준: `LOOP_ORCHESTRATION_POLICY.md`

## 추천 운영 방식

### A. 전국 일반 감시

- 목적: 신규 공고와 좋은 후보를 넓게 본다
- 권장 도구: `scan_sale_candidates`
- 현재 텔레그램 크론:
  - `매일 09:14`

### B. 서울 특화 정밀 노트북 감시

- 목적: 첨부 PDF까지 읽어 제조연월 / RAM / 모델 단서를 더 깊게 본다
- 현재 별도 스크립트:
  - `slb_laptop_selector.py`
- 이유:
  - 전국 MCP는 현재 공개 HTML/상세 공고 기준의 1차 선별기
  - 서울 특화 스크립트는 PDF 기반 추가 판독이 가능

즉 현재 구조는

- **전국 MCP = 넓게 보는 레이더**
- **서울 특화 selector = 깊게 파는 정밀 탐지기**

입니다.

## 점수/우선순위 해석

`scan_sale_candidates` 결과에는 다음 필드가 붙습니다.

- `asset_type`
  - 추정 자산 유형
- `model_candidates`
  - 제목/상세에서 뽑은 모델 힌트
- `matched_keywords`
  - 어떤 관심 키워드에 걸렸는지
- `priority`
  - `high`, `medium`, `watch`
- `reasons`
  - 왜 후보로 분류했는지

### priority 기준

- `high`
  - 노트북 / 맥북 / 아이패드 / 아이폰 등 직접 키워드
- `medium`
  - 비품 / 서버 / 전자기기 / 기계 / 설비 / 부동산 등 재판매 후보
- `watch`
  - 약한 키워드 일치 또는 재검토용

## 크론 운영 메모

- 전국 감시는 서울 전용 일반 감시와 기능이 겹치므로 중복 정리가 가능
- 다만 `slb_laptop_selector.py`는 PDF 기반이라 완전 대체가 아님
- 따라서 운영상:
  - 서울 일반 감시는 제거 가능
  - 서울 정밀 노트북 감시는 유지 가치가 있음

## 향후 확장 아이디어

- 첨부 PDF 다운로드 및 본문 OCR/텍스트 판독 전국 확대
- 모델명 인터넷 스펙 조회 연동
- 입찰가 vs 시세 비교 점수화
- 당근마켓 회전 가능성 점수
- 전국 법원 추가 확장
- 법원별 run history 대시보드

## 주의

- 공식 공개 공고만 읽습니다.
- 법률자문·투자자문이 아닙니다.
- 법원별 HTML 구조가 바뀌면 파서를 수정해야 합니다.
- 본 MCP는 1회 실행 후 종료되는 조회형 도구로 운용합니다.
