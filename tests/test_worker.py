from nationwide_rehab_sale_watch_mcp.worker import _positive_int


def test_worker_interval_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("SCAN_VALUE", "2")
    assert _positive_int("SCAN_VALUE", 360, 15, 1440) == 15

    monkeypatch.setenv("SCAN_VALUE", "9999")
    assert _positive_int("SCAN_VALUE", 360, 15, 1440) == 1440

    monkeypatch.setenv("SCAN_VALUE", "not-a-number")
    assert _positive_int("SCAN_VALUE", 360, 15, 1440) == 360
