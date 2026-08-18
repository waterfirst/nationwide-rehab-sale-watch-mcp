#!/usr/bin/env python3
from __future__ import annotations

import re
import time
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .pricing import calculate_valuation
from .storage import WatchStore, utc_now

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
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
INTEREST_MAP = {
    "notebook": ["노트북", "laptop", "맥북", "macbook", "컴퓨터", "pc"],
    "apple": ["애플", "apple", "아이폰", "iphone", "아이패드", "ipad", "맥북", "macbook", "맥미니", "imac"],
    "equipment": ["기계", "설비", "장비", "서버", "전자기기", "사무기기", "비품"],
    "jewelry": ["귀금속", "금", "은", "다이아몬드", "보석", "주얼리", "시계", "순금"],
    "real_estate": ["부동산", "공장", "토지", "건물"],
}
MODEL_PATTERNS = [
    r"\b[A-Z]{2,}[A-Z0-9\-]{2,}_[A-Z0-9]+\b",
    r"\b(?=[A-Za-z0-9-]*[A-Za-z])(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]{2,}-[A-Za-z0-9]{3,}\b",
    r"\bM[1234]\b",
    r"\bRTX\s?[0-9]{3,4}\b",
]

mcp = FastMCP("nationwide-rehab-sale-watch")
store = WatchStore()

_HTTP = requests.Session()
_HTTP.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
_HTTP.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
    ),
)


def _session() -> requests.Session:
    return _HTTP


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
    _validate_court_url(url)
    r = _session().get(url, timeout=25)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() in {"iso-8859-1", "ascii"}:
        r.encoding = r.apparent_encoding or "euc-kr"
    return r.text


def _validate_court_url(url: str) -> None:
    parsed = urlparse(url)
    allowed_hosts = {urlparse(cfg["base_url"]).hostname for cfg in COURTS.values()}
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise ValueError("지원되는 회생법원 HTTPS 주소만 조회할 수 있습니다.")


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


def _collect_with_diagnostics(
    courts: list[str],
    max_pages: int = 2,
    keyword: Optional[str] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    collected: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    max_pages = max(1, min(int(max_pages), 10))
    for court in courts:
        cfg = _court_cfg(court)
        started = time.monotonic()
        court_rows: list[dict[str, Any]] = []
        try:
            for page in range(1, max_pages + 1):
                url = cfg["list_url"] if page == 1 else f"{cfg['list_url']}?pageIndex={page}"
                rows = _parse_list(court, _fetch_html(url))
                if not rows:
                    break
                if keyword:
                    key = keyword.lower()
                    rows = [r for r in rows if key in (r["title"] + " " + r["agency"]).lower()]
                court_rows.extend(rows)
            store.record_source_health(
                court,
                ok=True,
                latency_ms=round((time.monotonic() - started) * 1000),
                rows_seen=len(court_rows),
            )
            collected.extend(court_rows)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append({"court_code": court, "message": message})
            store.record_source_health(
                court,
                ok=False,
                latency_ms=round((time.monotonic() - started) * 1000),
                error=message,
            )
    return collected, errors


def _interests_to_keywords(interests: Optional[list[str]]) -> list[str]:
    if not interests:
        interests = ["notebook", "apple", "equipment", "jewelry", "real_estate"]
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


def _extract_model_candidates(text: str) -> list[str]:
    found: list[str] = []
    for pattern in MODEL_PATTERNS:
        for match in re.findall(pattern, text, flags=re.I):
            cleaned = _clean(match.strip(" .,:;()[]"))
            if cleaned and cleaned not in found:
                found.append(cleaned)
    return found[:8]


def _infer_asset_type(text: str) -> str:
    low = text.lower()
    rules = [
        ("아이폰", "아이폰"),
        ("iphone", "아이폰"),
        ("아이패드", "아이패드"),
        ("ipad", "아이패드"),
        ("맥북", "맥북"),
        ("macbook", "맥북"),
        ("맥미니", "맥미니"),
        ("mac mini", "맥미니"),
        ("imac", "아이맥"),
        ("아이맥", "아이맥"),
        ("노트북", "노트북"),
        ("laptop", "노트북"),
        ("서버", "서버"),
        ("다이아몬드", "다이아몬드"),
        ("귀금속", "귀금속"),
        ("순금", "귀금속"),
        ("시계", "시계"),
        ("전자기기", "전자기기"),
        ("비품", "비품"),
        ("설비", "설비"),
        ("기계", "기계"),
        ("장비", "장비"),
        ("부동산", "부동산"),
        ("토지", "토지"),
        ("건물", "건물"),
        ("공장", "공장"),
    ]
    for key, value in rules:
        if key in low:
            return value
    return "미상"


def _classify_priority(asset_type: str, text: str, matched: list[str]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    low = text.lower()
    priority = "watch"
    if asset_type in {"맥북", "아이패드", "아이폰", "맥미니", "아이맥", "노트북"}:
        reasons.append(f"{asset_type} 직접 키워드")
        priority = "high"
    if any(x in low for x in ["apple", "애플", "macbook", "iphone", "ipad"]):
        reasons.append("Apple 계열 단서")
        priority = "high"
    if any(x in low for x in ["서버", "전자기기", "비품", "기계", "설비", "장비"]) and priority != "high":
        reasons.append("재판매 가능 물품 단서")
        priority = "medium"
    if asset_type in {"귀금속", "다이아몬드", "시계"}:
        reasons.append(f"{asset_type} 시세 비교 가능")
        priority = "high"
    if any(x in low for x in ["부동산", "토지", "건물", "공장"]) and priority == "watch":
        reasons.append("부동산/공장 자산")
        priority = "medium"
    if matched and not reasons:
        reasons.append("관심 키워드 일치")
    return priority, reasons


def _score_candidate(item: dict[str, Any], keywords: list[str], interests: Optional[list[str]] = None) -> dict[str, Any]:
    text = (item["title"] + " " + item["agency"]).lower()
    matched = [kw for kw in keywords if kw.lower() in text]
    score = len(matched)
    selected = set(interests or [])
    if ("notebook" in selected or "apple" in selected) and any(x in text for x in ["노트북", "맥북", "아이패드", "아이폰", "macbook", "iphone", "ipad"]):
        score += 2
    if "equipment" in selected and any(x in text for x in ["설비", "기계", "장비", "서버", "전자기기", "사무기기", "비품"]):
        score += 1
    if "jewelry" in selected and any(x in text for x in ["귀금속", "다이아몬드", "보석", "순금", "시계"]):
        score += 2
    if "real_estate" in selected and any(x in text for x in ["부동산", "공장", "토지", "건물"]):
        score += 1
    asset_type = _infer_asset_type(text)
    model_candidates = _extract_model_candidates(item["title"] + " " + item["agency"])
    priority, reasons = _classify_priority(asset_type, text, matched)
    if model_candidates:
        score += 1
        reasons.append(f"모델 단서 {model_candidates[0]}")
    return {
        **item,
        "asset_type": asset_type,
        "model_candidates": model_candidates,
        "matched_keywords": matched,
        "priority": priority,
        "reasons": reasons,
        "score": score,
    }


def _enrich_candidate_detail(item: dict[str, Any]) -> dict[str, Any]:
    url = item.get("url")
    if not url:
        return item
    try:
        detail = _parse_detail(_fetch_html(url), fallback_url=url)
        body = detail.get("body_excerpt", "")
        if item.get("asset_type") == "미상":
            item["asset_type"] = _infer_asset_type(body)
        extra_models = _extract_model_candidates(body)
        if extra_models:
            merged = list(dict.fromkeys((item.get("model_candidates") or []) + extra_models))
            item["model_candidates"] = merged[:8]
        item["written_at"] = detail.get("written_at", "")
        item["expires_at"] = detail.get("expires_at", "")
        item["phone"] = detail.get("phone", "")
    except Exception:
        pass
    return item


def run_persistent_scan(
    courts: Optional[list[str]] = None,
    *,
    interests: Optional[list[str]] = None,
    max_pages: int = 2,
    enrich_details: bool = False,
) -> dict[str, Any]:
    """Collect each source independently and durably upsert every observed notice."""
    selected = _normalize_courts(courts)
    run_id = store.start_scan(selected)
    observed_at = utc_now()
    keywords = _interests_to_keywords(interests)
    items, errors = _collect_with_diagnostics(selected, max_pages=max_pages)
    candidates: list[dict[str, Any]] = []
    fresh_items: list[dict[str, Any]] = []
    new_count = 0
    try:
        for item in items:
            profiled = _score_candidate(
                item,
                keywords,
                interests=interests or ["notebook", "apple", "equipment", "jewelry"],
            )
            if enrich_details and profiled["score"] > 0:
                profiled = _enrich_candidate_detail(profiled)
            listing_id, created = store.upsert_listing(profiled, observed_at=observed_at)
            profiled["listing_id"] = listing_id
            profiled["is_new"] = created
            new_count += int(created)
            if created:
                fresh_items.append(profiled)
            if profiled["score"] > 0:
                candidates.append(profiled)
        status = "success" if not errors else ("partial" if items else "failed")
        store.finish_scan(
            run_id,
            status=status,
            rows_seen=len(items),
            new_count=new_count,
            candidate_count=len(candidates),
            errors=errors,
        )
    except Exception as exc:
        errors.append({"court_code": "storage", "message": f"{type(exc).__name__}: {exc}"})
        store.finish_scan(
            run_id,
            status="failed",
            rows_seen=len(items),
            new_count=new_count,
            candidate_count=len(candidates),
            errors=errors,
        )
        raise
    priority_order = {"high": 0, "medium": 1, "watch": 2}
    candidates.sort(
        key=lambda x: (
            priority_order.get(x.get("priority", "watch"), 9),
            -x.get("score", 0),
            x.get("court_name", ""),
            x.get("title", ""),
        )
    )
    return {
        "run_id": run_id,
        "status": status,
        "courts": selected,
        "rows_seen": len(items),
        "new_count": new_count,
        "candidate_count": len(candidates),
        "items": candidates,
        "new_items": fresh_items,
        "errors": errors,
        "observed_at": observed_at,
        "database": str(store.path),
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
    items, errors = _collect_with_diagnostics(selected, max_pages=max_pages, keyword=keyword)
    if len(selected) > 1:
        items = _interleave_by_court(items, selected)
    items = items[: max(1, min(limit, 100))]
    return {
        "courts": selected,
        "count": len(items),
        "items": items,
        "status": "success" if not errors else ("partial" if items else "failed"),
        "errors": errors,
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
    """SQLite 전체 이력 대비 신규 공고만 반환하고 수집 이력을 남긴다."""
    result = run_persistent_scan(courts, max_pages=max_pages)
    fresh = result["new_items"]
    if keyword:
        key = keyword.lower()
        fresh = [item for item in fresh if key in (item["title"] + " " + item["agency"]).lower()]
    fresh = fresh[: max(1, min(limit, 100))]
    return {
        "courts": result["courts"],
        "count": len(fresh),
        "items": fresh,
        "scan_status": result["status"],
        "errors": result["errors"],
        "database": str(store.path),
        "disclaimer": "공식 공개 공고 조회 결과. 법률자문 아님.",
    }


@mcp.tool()
def scan_sale_candidates(
    courts: Optional[list[str]] = None,
    limit: int = 20,
    interests: Optional[list[str]] = None,
    max_pages: int = 2,
) -> dict[str, Any]:
    """관심 품목 후보를 선별하고 SQLite에 누적 저장한다."""
    result = run_persistent_scan(
        courts,
        interests=interests,
        max_pages=max_pages,
        enrich_details=True,
    )
    ranked = result["items"][: max(1, min(limit, 100))]
    return {
        "courts": result["courts"],
        "interests": interests or ["notebook", "apple", "equipment", "jewelry", "real_estate"],
        "count": len(ranked),
        "items": ranked,
        "scan_status": result["status"],
        "new_count": result["new_count"],
        "rows_seen": result["rows_seen"],
        "errors": result["errors"],
        "database": str(store.path),
        "disclaimer": "제목/기관 기준 1차 자동선별 결과. 입찰 전 원문 확인 필요.",
    }


@mcp.tool()
def get_watch_dashboard(limit: int = 50) -> dict[str, Any]:
    """누적된 공고, 수집 상태, 시세 분석 요약을 반환한다."""
    payload = store.dashboard()
    payload["listings"] = payload["listings"][: max(1, min(limit, 200))]
    payload["database"] = str(store.path)
    return payload


@mcp.tool()
def recommend_bid_price(
    market_prices: list[int],
    condition_ratio: float = 0.92,
    negotiation_ratio: float = 0.96,
    selling_fee_ratio: float = 0.04,
    acquisition_fee_ratio: float = 0.02,
    repair_cost: int = 50_000,
    logistics_cost: int = 30_000,
    risk_ratio: float = 0.10,
    target_margin_ratio: float = 0.18,
) -> dict[str, Any]:
    """사용자가 확인한 중고 시세로 최대 입찰가와 권장 판매가를 추정한다."""
    result = calculate_valuation(
        market_prices,
        {
            "condition_ratio": condition_ratio,
            "negotiation_ratio": negotiation_ratio,
            "selling_fee_ratio": selling_fee_ratio,
            "acquisition_fee_ratio": acquisition_fee_ratio,
            "repair_cost": repair_cost,
            "logistics_cost": logistics_cost,
            "risk_ratio": risk_ratio,
            "target_margin_ratio": target_margin_ratio,
        },
    )
    return {
        **result,
        "disclaimer": "입력한 시세와 가정에 따른 의사결정 보조값입니다. 실물·권리·세금·입찰조건은 별도로 확인하세요.",
    }


if __name__ == "__main__":
    mcp.run()
