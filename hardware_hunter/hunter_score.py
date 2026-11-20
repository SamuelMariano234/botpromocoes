from __future__ import annotations

from dataclasses import dataclass

from hardware_hunter.models import Offer
from hardware_hunter.risk_analyzer import analyze_risk


@dataclass
class Score:
    value: int
    risk: str
    explanation: list[str]


def calculate_score(offer: Offer, reference_price: float | None = None,
                    history_median: float | None = None) -> Score:
    # Conservative scoring: missing data earns no points, and risk is a direct penalty.
    price_ref = history_median or reference_price
    price_points = 0
    explanation = []
    if price_ref and price_ref > 0:
        discount = max(0, (price_ref - offer.total_price) / price_ref)
        price_points = round(min(30, discount * 100))
        explanation.append(f"Preço: {discount:.0%} abaixo da referência")
    else:
        explanation.append("Preço: referência insuficiente")
    history_points = 12 if history_median and reference_price else (6 if history_median or reference_price else 0)
    quality = 8 if offer.seller_reputation else 0
    potential = min(15, round(max(0, ((price_ref or offer.total_price) - offer.total_price) / max(price_ref or offer.total_price, 1) * 60)))
    reliability = 5 + (3 if offer.condition else 0) + (2 if offer.shipping is not None else 0)
    if offer.seller_reputation: quality += 4
    risk = analyze_risk(offer, price_ref)
    raw = price_points + history_points + quality + potential + reliability
    value = max(0, min(100, raw - risk.penalty))
    explanation.extend([f"Histórico e dados comparáveis: {history_points}/20",
                        f"Vendedor/anúncio: {quality}/15", f"Risco {risk.level}: −{risk.penalty}"])
    explanation.extend(risk.reasons)
    return Score(value, risk.level, explanation)

