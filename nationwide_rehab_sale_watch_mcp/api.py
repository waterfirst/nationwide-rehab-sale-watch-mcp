from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .pricing import DEFAULT_ASSUMPTIONS, calculate_valuation
from .server import COURTS, run_persistent_scan, store


class ScanRequest(BaseModel):
    courts: list[str] | None = None
    interests: list[str] | None = None
    max_pages: int = Field(default=2, ge=1, le=10)
    enrich_details: bool = False

    @field_validator("courts")
    @classmethod
    def validate_courts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        invalid = sorted(set(value) - set(COURTS))
        if invalid:
            raise ValueError(f"지원하지 않는 법원 코드: {', '.join(invalid)}")
        return value


class ComparableRequest(BaseModel):
    source: Literal["당근", "번개장터", "중고나라", "기타"]
    title: str = Field(min_length=2, max_length=200)
    price: int = Field(gt=0, le=10_000_000_000)
    condition_label: str = Field(default="중고 A급", max_length=40)
    source_url: str | None = Field(default=None, max_length=1000)

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("유효한 HTTP(S) 주소를 입력하세요.")
        return value


class ValuationRequest(BaseModel):
    market_prices: list[int] = Field(min_length=1, max_length=100)
    assumptions: dict[str, float | int] = Field(default_factory=dict)


class SavedValuationRequest(BaseModel):
    assumptions: dict[str, float | int] = Field(default_factory=dict)


app = FastAPI(
    title="리세일 레이더 API",
    version="1.0.0",
    description="회생법원 자산 공고 수집, 시세 근거 관리, 입찰가 추천 API",
)

allowed_origins = [
    item.strip()
    for item in os.getenv("REHAB_WATCH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    dashboard = store.dashboard()
    source_count = len(dashboard["sources"])
    failing_sources = sum(1 for source in dashboard["sources"] if source["consecutive_failures"] > 0)
    return {
        "status": "ok" if failing_sources == 0 else "degraded",
        "database_ready": store.path.exists(),
        "database_path": str(store.path),
        "configured_sources": len(COURTS),
        "observed_sources": source_count,
        "failing_sources": failing_sources,
    }


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    payload = store.dashboard()
    known = {source["court_code"]: source for source in payload["sources"]}
    payload["sources"] = [
        {
            "court_code": code,
            "court_name": config["name"],
            "status": (
                "never" if code not in known else
                "error" if known[code]["consecutive_failures"] > 0 else "healthy"
            ),
            **known.get(code, {}),
        }
        for code, config in COURTS.items()
    ]
    payload["meta"] = {
        "product_name": "리세일 레이더",
        "data_mode": "live" if payload["runs"] else "empty",
        "disclaimer": "시세·입찰가는 의사결정 보조값입니다. 입찰 전 실물, 권리, 세금, 공고 원문을 확인하세요.",
    }
    return payload


@app.post("/api/scans")
async def scan(request: ScanRequest) -> dict[str, Any]:
    result = await run_in_threadpool(
        run_persistent_scan,
        request.courts,
        interests=request.interests,
        max_pages=request.max_pages,
        enrich_details=request.enrich_details,
    )
    return {
        key: value
        for key, value in result.items()
        if key not in {"items", "new_items", "database"}
    }


@app.get("/api/listings")
def listings(
    limit: int = Query(default=60, ge=1, le=200),
    priority: str | None = None,
    court: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    items = store.list_listings(limit=limit, priority=priority, court=court, query=query)
    return {"count": len(items), "items": items}


@app.get("/api/listings/{listing_id}")
def listing_detail(listing_id: int) -> dict[str, Any]:
    listing = store.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")
    return listing


@app.post("/api/listings/{listing_id}/comparables", status_code=201)
def add_comparable(listing_id: int, request: ComparableRequest) -> dict[str, Any]:
    if not store.get_listing(listing_id):
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")
    return store.add_comparable(listing_id, **request.model_dump())


@app.post("/api/valuations/preview")
def valuation_preview(request: ValuationRequest) -> dict[str, Any]:
    try:
        return calculate_valuation(request.market_prices, request.assumptions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/listings/{listing_id}/valuation", status_code=201)
def save_valuation(listing_id: int, request: SavedValuationRequest) -> dict[str, Any]:
    listing = store.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")
    prices = [item["price"] for item in listing["comparables"]]
    try:
        result = calculate_valuation(prices, {**DEFAULT_ASSUMPTIONS, **request.assumptions})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save_valuation(listing_id, result)
    return result


web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
if web_dist.exists():
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
