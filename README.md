# 전국 회생법원 매각 매물 조회 MCP

서울회생법원 전용 스크립트를 전국 공통형으로 확장한 로컬 MCP 서버입니다.

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

## 실행

```bash
python -m nationwide_rehab_sale_watch_mcp.server
```

## 운영 문서

- 연결 규칙: `COURT_CONNECTION_RULES.md`
- 루프/종료 기준: `LOOP_ORCHESTRATION_POLICY.md`

## 주의

- 공식 공개 공고만 읽습니다.
- 법률자문·투자자문이 아닙니다.
- 법원별 HTML 구조가 바뀌면 파서를 수정해야 합니다.
- 본 MCP는 1회 실행 후 종료되는 조회형 도구로 운용합니다.
