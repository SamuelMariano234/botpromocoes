from __future__ import annotations

from hardware_hunter.models import Offer
from hardware_hunter.product_matcher import matches_offer


def accepts(offer: Offer, query: str, max_price: float | None = None,
            exclusions: tuple[str, ...] = ()) -> bool:
    if max_price is not None and offer.total_price > max_price: return False
    return matches_offer(offer.title, query, exclusions or __import__("hardware_hunter.product_matcher", fromlist=["DEFAULT_EXCLUSIONS"]).DEFAULT_EXCLUSIONS)

