# 전국 회생법원 연결 규칙

## 1. 지원 법원 코드

- `slb` : 서울회생법원
- `swb` : 수원회생법원
- `bsb` : 부산회생법원
- `dgb` : 대구회생법원
- `djb` : 대전회생법원
- `gjb` : 광주회생법원

## 2. URL 규칙

모든 법원은 같은 패턴을 따른다.

- 목록:
  - `https://{court}.scourt.go.kr/rel/realboard/DcRealListAction.work`
- 상세:
  - `https://{court}.scourt.go.kr/rel/realboard/RealboardView.work?seq_id={seq_id}`

즉 court 코드만 바꾸면 전국 공통 파서로 조회 가능하다.

## 3. 파싱 규칙

- 목록 표: `table.tableHor`
- 상세 표: `table.tableVer`
- 기본 인코딩: `euc-kr`
- 기본 키:
  - `매각기관`
  - `관할법원`
  - `제목`
  - `조회수`
  - `작성일`
  - `공고만료일`
  - `첨부파일`
  - `전화번호`

## 4. 관심 품목 1차 선별 규칙

### notebook
- `노트북`, `laptop`, `맥북`, `macbook`, `컴퓨터`, `pc`

### apple
- `애플`, `apple`, `아이폰`, `iphone`, `아이패드`, `ipad`, `맥북`, `macbook`, `맥미니`, `imac`

### equipment
- `기계`, `설비`, `장비`, `서버`, `전자기기`, `사무기기`, `비품`

### real_estate
- `부동산`, `공장`, `토지`, `건물`

## 5. 다중 법원 조회 규칙

- 여러 법원을 함께 조회할 때는 한 법원 결과만 앞에 몰리지 않도록
  **court interleave** 방식으로 섞어 반환한다.
- 신규 공고 비교 상태도 법원별로 따로 저장한다.

## 6. 상태 저장 규칙

- 상태 파일:
  - `records/last_seen.json`
- 구조:
  - `seen_by_court.{court_code} = [seq_id, ...]`

## 7. 운영 규칙

- 본 MCP는 **공개 공고 조회 전용**
- 법률자문/투자자문 아님
- 1회 실행 후 종료
- 구조 변경 시 court 공통 파서 우선 수정
