from nationwide_rehab_sale_watch_mcp.storage import WatchStore


def sample_listing() -> dict:
    return {
        "court_code": "slb",
        "court_name": "서울회생법원",
        "seq_id": "1234",
        "title": "노트북 및 전자기기 매각 공고",
        "agency": "파산관재인",
        "url": "https://slb.scourt.go.kr/rel/realboard/RealboardView.work?seq_id=1234",
        "asset_type": "노트북",
        "priority": "high",
        "score": 4,
        "views": "1,204",
    }


def test_listing_history_is_durable_and_deduplicated(tmp_path) -> None:
    store = WatchStore(tmp_path / "watch.db")

    listing_id, created = store.upsert_listing(sample_listing(), "2026-08-18T01:00:00+00:00")
    same_id, created_again = store.upsert_listing(sample_listing(), "2026-08-18T02:00:00+00:00")

    assert created is True
    assert created_again is False
    assert same_id == listing_id
    assert store.dashboard()["stats"]["total"] == 1


def test_comparables_and_valuation_are_linked_to_listing(tmp_path) -> None:
    store = WatchStore(tmp_path / "watch.db")
    listing_id, _ = store.upsert_listing(sample_listing())
    store.add_comparable(listing_id, source="당근", title="비교 매물", price=800_000)

    detail = store.get_listing(listing_id)

    assert detail is not None
    assert detail["comparables"][0]["price"] == 800_000
