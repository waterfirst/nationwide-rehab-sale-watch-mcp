from fastapi.testclient import TestClient

from nationwide_rehab_sale_watch_mcp import api
from nationwide_rehab_sale_watch_mcp.storage import WatchStore


def test_market_evidence_to_saved_valuation_flow(tmp_path, monkeypatch) -> None:
    test_store = WatchStore(tmp_path / "api.db")
    monkeypatch.setattr(api, "store", test_store)
    listing_id, _ = test_store.upsert_listing(
        {
            "court_code": "slb",
            "court_name": "서울회생법원",
            "seq_id": "api-1",
            "title": "맥북 프로 매각 공고",
            "agency": "파산관재인",
            "url": "https://slb.scourt.go.kr/rel/realboard/RealboardView.work?seq_id=api-1",
            "asset_type": "맥북",
            "priority": "high",
            "score": 5,
        }
    )
    client = TestClient(api.app)

    for source, price in [("당근", 900_000), ("번개장터", 950_000), ("중고나라", 1_000_000)]:
        response = client.post(
            f"/api/listings/{listing_id}/comparables",
            json={"source": source, "title": "맥북 프로 14 중고", "price": price},
        )
        assert response.status_code == 201

    valuation = client.post(f"/api/listings/{listing_id}/valuation", json={"assumptions": {}})

    assert valuation.status_code == 201
    assert valuation.json()["max_bid_price"] > 0
    assert client.get("/api/dashboard").json()["stats"]["valued"] == 1
