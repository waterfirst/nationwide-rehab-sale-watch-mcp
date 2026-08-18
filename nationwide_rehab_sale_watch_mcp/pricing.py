from __future__ import annotations

import math
import statistics
from typing import Any, Iterable


DEFAULT_ASSUMPTIONS: dict[str, float | int] = {
    "condition_ratio": 0.92,
    "negotiation_ratio": 0.96,
    "selling_fee_ratio": 0.04,
    "acquisition_fee_ratio": 0.02,
    "repair_cost": 50_000,
    "logistics_cost": 30_000,
    "risk_ratio": 0.10,
    "target_margin_ratio": 0.18,
}


def _round_price(value: float, unit: int = 10_000) -> int:
    if value <= 0:
        return 0
    return int(round(value / unit) * unit)


def _clean_prices(prices: Iterable[int | float]) -> list[int]:
    cleaned = sorted(int(price) for price in prices if price and price > 0)
    if len(cleaned) < 4:
        return cleaned
    q1, _, q3 = statistics.quantiles(cleaned, n=4, method="inclusive")
    spread = q3 - q1
    low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
    filtered = [price for price in cleaned if low <= price <= high]
    return filtered or cleaned


def calculate_valuation(
    prices: Iterable[int | float],
    assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a conservative resale recommendation from user-supplied comparables.

    The engine intentionally uses asking-price evidence only as an input. It does
    not claim that marketplace asking prices are completed transaction prices.
    """

    values = _clean_prices(prices)
    if not values:
        raise ValueError("시세 비교가가 1건 이상 필요합니다.")

    merged: dict[str, float | int] = {**DEFAULT_ASSUMPTIONS, **(assumptions or {})}
    ratios = (
        "condition_ratio",
        "negotiation_ratio",
        "selling_fee_ratio",
        "acquisition_fee_ratio",
        "risk_ratio",
        "target_margin_ratio",
    )
    for key in ratios:
        merged[key] = float(merged[key])
    for key in ("repair_cost", "logistics_cost"):
        merged[key] = max(0, int(merged[key]))

    if not 0.4 <= merged["condition_ratio"] <= 1.2:
        raise ValueError("상태 보정계수는 0.4~1.2 범위여야 합니다.")
    if not 0.5 <= merged["negotiation_ratio"] <= 1.0:
        raise ValueError("협상 체결률은 0.5~1.0 범위여야 합니다.")
    for key in ("selling_fee_ratio", "acquisition_fee_ratio", "risk_ratio", "target_margin_ratio"):
        if not 0 <= merged[key] <= 0.5:
            raise ValueError(f"{key}는 0~0.5 범위여야 합니다.")

    market_median = statistics.median(values)
    recommended_sale = market_median * merged["condition_ratio"]
    expected_sale = recommended_sale * merged["negotiation_ratio"]
    selling_fee = expected_sale * merged["selling_fee_ratio"]
    risk_buffer = expected_sale * merged["risk_ratio"]
    target_profit = expected_sale * merged["target_margin_ratio"]
    fixed_cost = merged["repair_cost"] + merged["logistics_cost"]
    affordable_total = expected_sale - selling_fee - risk_buffer - target_profit - fixed_cost
    max_bid = max(0, affordable_total / (1 + merged["acquisition_fee_ratio"]))
    acquisition_fee = max_bid * merged["acquisition_fee_ratio"]
    expected_profit = expected_sale - selling_fee - fixed_cost - max_bid - acquisition_fee - risk_buffer

    dispersion = statistics.pstdev(values) / market_median if len(values) > 1 and market_median else 1.0
    sample_score = min(70, len(values) * 14)
    dispersion_penalty = min(35, round(dispersion * 100))
    confidence = max(15, min(95, sample_score + 25 - dispersion_penalty))
    if len(values) < 3:
        confidence = min(confidence, 45)

    roi = expected_profit / max_bid if max_bid else 0
    opportunity_score = round(
        max(0, min(100, 42 + roi * 70 + confidence * 0.25 - dispersion * 35))
    )

    return {
        "market_median": _round_price(market_median),
        "recommended_sale_price": _round_price(recommended_sale),
        "expected_sale_price": _round_price(expected_sale),
        "max_bid_price": _round_price(max_bid),
        "expected_profit": _round_price(expected_profit),
        "expected_roi_ratio": round(roi, 4),
        "confidence": confidence,
        "opportunity_score": opportunity_score,
        "comparable_count": len(values),
        "price_min": min(values),
        "price_max": max(values),
        "price_dispersion_ratio": round(dispersion, 4) if math.isfinite(dispersion) else 1.0,
        "assumptions": merged,
        "formula_note": "완료거래가가 아닌 입력 시세의 중앙값에 상태·협상·수수료·수리·물류·위험·목표이익을 차감한 보수적 추정치",
    }
