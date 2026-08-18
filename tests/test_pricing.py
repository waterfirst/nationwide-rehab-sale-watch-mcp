import pytest

from nationwide_rehab_sale_watch_mcp.pricing import calculate_valuation


def test_calculate_valuation_produces_conservative_bid() -> None:
    result = calculate_valuation([900_000, 1_000_000, 1_050_000, 7_000_000])

    assert result["market_median"] == 1_000_000
    assert result["recommended_sale_price"] <= result["market_median"]
    assert 0 < result["max_bid_price"] < result["expected_sale_price"]
    assert result["expected_profit"] > 0
    assert result["comparable_count"] == 3
    assert 15 <= result["confidence"] <= 95


def test_calculate_valuation_requires_evidence() -> None:
    with pytest.raises(ValueError, match="시세"):
        calculate_valuation([])


def test_calculate_valuation_validates_ratios() -> None:
    with pytest.raises(ValueError, match="상태"):
        calculate_valuation([1_000_000], {"condition_ratio": 0.1})
