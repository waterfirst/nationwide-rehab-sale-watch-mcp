#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from mcp.server.fastmcp import FastMCP
except Exception:
    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def tool(self, *_args: Any, **_kwargs: Any):
            def decorator(fn):
                return fn
            return decorator

        def run(self) -> None:
            raise SystemExit("mcp SDK가 필요합니다: pip install 'mcp[cli]'")


COURTS: dict[str, dict[str, str]] = {
    "slb": {"name": "서울회생법원", "base_url": "https://slb.scourt.go.kr"},
    "swb": {"name": "수원회생법원", "base_url": "https://swb.scourt.go.kr"},
    "bsb": {"name": "부산회생법원", "base_url": "https://bsb.scourt.go.kr"},
    "dgb": {"name": "대구회생법원", "base_url": "https://dgb.scourt.go.kr"},
    "djb": {"name": "대전회생법원", "base_url": "https://djb.scourt.go.kr"},
    "gjb": {"name": "광주회생법원", "base_url": "https://gjb.scourt.go.kr"},
}
STATE_PATH = Path("/home/waterfirst/.codex/mcp_servers/nationwide-rehab-sale-watch/records/last_seen.json")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
INTEREST_MAP = {
    "notebook": ["노트북", "laptop", "맥북", "macbook", "컴퓨터", "pc"],
    "apple": ["애플", "apple", "아이폰", "iphone", "아이패드", "ipad", "맥북", "macbook", "맥미니", "imac"],
    "equipment": ["기계", "설비", "장비", "서버", "전자기기", "사무기기", "비품"],
    "real_estate": ["부동산", "공장", "토지", "건물"],
}

mcp = FastMCP("nationwide-rehab-sale-watch")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _court_cfg(court: str) -> dict[str, str]:
    if court not in COURTS:
        raise ValueError(f"지원하지 않는 court 코드: {court}")
    cfg = COURTS[court].copy()
    cfg["list_url"] = f"{cfg['base_url']}/rel/realboard/DcRealListAction.work"
    cfg["view_url"] = f"{cfg['base_url']}/rel/realboard/RealboardView.work"
    return cfg


def _fetch_html(url: str) -> str:
    r = _session().get(url, timeout=25)
    r.raise_for_status()
    r.encoding = "euc-kr"
    return r.text


def _extract_seq_id(url: str | None) -> Optional[str]:
    if not url:
        return None
    qs = parse_qs(urlparse(url).query)
    seqs = qs.get("seq_id")
    return seqs[0] if seqs else None


def _parse_list(court: str, html: str) -> list[dict[str, Any]]:
    base_url = COURTS[court]["base_url"]
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for tr in soup.select("table.tableHor tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        link = tr.find("a", href=True)
        title = _clean(tds[3].get_text(" ", strip=True))
        url = urljoin(base_url, link.get("href")) if link else None
        rows.append(
            {
                "court_code": court,
                "court_name": COURTS[court]["name"],
                "no": tds[0].get_text(strip=True),
                "court": tds[1].get_text(strip=True),
                "agency": _clean(tds[2].get_text(" ", strip=True)),
                "title": title,
                "views": tds[4].get_text(strip=True),
                "url": url,
                "seq_id": _extract_seq_id(url),
            }
        )
    return rows


def _parse_detail(html: str, fallback_url: str | None = None) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.tableVer")
    fields: dict[str, str] = {}
    if table:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            i = 0
            while i + 1 < len(cells):
                if cells[i].name == "th" and cells[i + 1].name == "td":
                    fields[_clean(cells[i].get_text(" ", strip=True))] = _clean(cells[i + 1].get_text(" ", strip=True))
                    i += 2
                else:
                    i += 1
    body_text = _clean(soup.get_text(" ", strip=True))
    return {
        "title": fields.get("제목"),
        "written_at": fields.get("작성일", ""),
        "expires_at": fields.get("공고만료일", ""),
        "phone": fields.get("전화번호", ""),
        "agency": fields.get("매각기관", ""),
        "source_url": fallback_url,
        "fields": fields,
        "body_excerpt": body_text[:1600],
    }


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"seen_by_court": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_by_court": {}}


def _save_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_courts(courts: Optional[list[str]]) -> list[str]:
    if not courts:
        return list(COURTS.keys())
    values = []
    for court in courts:
        court = court.strip().lower()
        if court in COURTS and court not in values:
            values.append(court)
    if not values:
        raise ValueError("유효한 court 코드가 없습니다.")
    return values


def _collect(courts: list[str], max_pages: int = 2, keyword: Optional[str] = None) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for court in courts:
        cfg = _court_cfg(court)
        for page in range(1, max_pages + 1):
            url = cfg["list_url"] if page == 1 else f"{cfg['list_url']}?pageIndex={page}"
            rows = _parse_list(court, _fetch_html(url))
            if not rows:
                break
            if keyword:
                key = keyword.lower()
                rows = [r for r in rows if key in (r["title"] + " " + r["agency"]).lower()]
            collected.extend(rows)
    return collected


def _interests_to_keywords(interests: Optional[list[str]]) -> list[str]:
    if not interests:
        interests = ["notebook", "apple", "equipment", "real_estate"]
    keywords: list[str] = []
    for interest in interests:
        for kw in INTEREST_MAP.get(interest, []):
            if kw not in keywords:
                keywords.append(kw)
    return keywords


def _interleave_by_court(items: list[dict[str, Any]], courts: list[str]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {court: [] for court in courts}
    for item in items:
        court = item.get("court_code")
        if court in buckets:
            buckets[court].append(item)
    merged: list[dict[str, Any]] = []
    while True:
        progressed = False
        for court in courts:
            if buckets[court]:
                merged.append(buckets[court].pop(0))
                progressed = True
        if not progressed:
            break
    return merged


def _score_candidate(item: dict[str, Any], keywords: list[str], interests: Optional[list[str]] = None) -> dict[str, Any]:
    text = (item["title"] + " " + item["agency"]).lower()
    matched = [kw for kw in keywords if kw.lower() in text]
    score = len(matched)
    selected = set(interests or [])
    if ("notebook" in selected or "apple" in selected) and any(x in text for x in ["노트북", "맥북", "아이패드", "아이폰", "macbook", "iphone", "ipad"]):
        score += 2
    if "equipment" in selected and any(x in text for x in ["설비", "기계", "장비", "서버", "전자기기", "사무기기", "비품"]):
        score += 1
    if "real_estate" in selected and any(x in text for x in ["부동산", "공장", "토지", "건물"]):
        score += 1
    return {
        **item,
        "matched_keywords": matched,
        "score": score,
    }


@mcp.tool()
def list_courts() -> dict[str, Any]:
    """지원하는 회생법원 코드 목록을 반환한다."""
    return {
        "count": len(COURTS),
        "items": [{"court_code": code, **cfg} for code, cfg in COURTS.items()],
    }


@mcp.tool()
def list_sale_notices(
    courts: Optional[list[str]] = None,
    limit: int = 20,
    keyword: Optional[str] = None,
    max_pages: int = 2,
) -> dict[str, Any]:
    """여러 회생법원의 최신 매각 공고를 통합 조회한다."""
    selected = _normalize_courts(courts)
    items = _collect(selected, max_pages=max_pages, keyword=keyword)
    if len(selected) > 1:
        items = _interleave_by_court(items, selected)
    items = items[: max(1, min(limit, 100))]
    return {
        "courts": selected,
        "count": len(items),
        "items": items,
        "disclaimer": "공식 공개 공고 조회 결과. 법률자문 아님.",
    }


@mcp.tool()
def get_sale_notice_detail(
    court: Optional[str] = None,
    seq_id: Optional[str] = None,
    url: Optional[str] = None,
) -> dict[str, Any]:
    """개별 공고 상세를 조회한다. url이 있으면 court 없이도 가능하다."""
    if not url and not (court and seq_id):
        return {"error": "url 또는 court+seq_id가 필요합니다."}
    detail_url = url
    if not detail_url:
        cfg = _court_cfg((court or "").lower())
        detail_url = f"{cfg['view_url']}?seq_id={seq_id}"
    html = _fetch_html(detail_url)
    detail = _parse_detail(html, fallback_url=detail_url)
    if court:
        detail["court_code"] = court.lower()
        detail["court_name"] = COURTS[court.lower()]["name"]
    if seq_id:
        detail["seq_id"] = seq_id
    return {
        "detail": detail,
        "disclaimer": "공식 공개 공고 조회 결과. 법률자문 아님.",
    }


@mcp.tool()
def list_new_sale_notices(
    courts: Optional[list[str]] = None,
    limit: int = 20,
    keyword: Optional[str] = None,
    max_pages: int = 2,
) -> dict[str, Any]:
    """직전 스냅샷 대비 신규 공고만 조회하고 상태를 갱신한다."""
    selected = _normalize_courts(courts)
    items = _collect(selected, max_pages=max_pages, keyword=keyword)
    state = _load_state()
    seen_by_court = state.get("seen_by_court", {})
    fresh: list[dict[str, Any]] = []
    next_seen: dict[str, list[str]] = dict(seen_by_court)
    for court in selected:
        court_items = [x for x in items if x["court_code"] == court and x.get("seq_id")]
        seen = set(seen_by_court.get(court, []))
        fresh.extend([x for x in court_items if x["seq_id"] not in seen])
        next_seen[court] = [x["seq_id"] for x in court_items if x.get("seq_id")]
    _save_state({"seen_by_court": next_seen})
    if len(selected) > 1:
        fresh = _interleave_by_court(fresh, selected)
    fresh = fresh[: max(1, min(limit, 100))]
    return {
        "courts": selected,
        "count": len(fresh),
        "items": fresh,
        "state_path": str(STATE_PATH),
        "disclaimer": "공식 공개 공고 조회 결과. 법률자문 아님.",
    }


@mcp.tool()
def scan_sale_candidates(
    courts: Optional[list[str]] = None,
    limit: int = 20,
    interests: Optional[list[str]] = None,
    max_pages: int = 2,
) -> dict[str, Any]:
    """관심 품목 중심으로 전국 회생법원 공고 후보를 추린다."""
    selected = _normalize_courts(courts)
    keywords = _interests_to_keywords(interests)
    items = _collect(selected, max_pages=max_pages)
    ranked = []
    for item in items:
        profiled = _score_candidate(item, keywords, interests=interests or ["notebook", "apple", "equipment", "real_estate"])
        if profiled["score"] > 0:
            ranked.append(profiled)
    ranked.sort(key=lambda x: (-x["score"], x["court_name"], x["title"]))
    ranked = ranked[: max(1, min(limit, 100))]
    return {
        "courts": selected,
        "interests": interests or ["notebook", "apple", "equipment", "real_estate"],
        "count": len(ranked),
        "items": ranked,
        "disclaimer": "제목/기관 기준 1차 자동선별 결과. 입찰 전 원문 확인 필요.",
    }
