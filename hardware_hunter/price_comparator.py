from __future__ import annotations

from hardware_hunter.models import Offer


def compare(offers: list[Offer]) -> list[Offer]:
    """Sort equivalent candidate listings by total price, with unknown shipping last-ish."""
    return sorted(offers, key=lambda o: (o.total_price if o.shipping is not None else o.price + 1_000_000, o.marketplace))

