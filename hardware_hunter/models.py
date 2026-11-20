from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Offer:
    marketplace: str
    title: str
    price: float
    url: str
    item_id: str
    condition: str | None = None
    shipping: float | None = None
    seller: str | None = None
    seller_reputation: str | None = None
    published_at: str | None = None
    description: str | None = None
    product_key: str = ""
    first_seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def total_price(self) -> float:
        return self.price + (self.shipping or 0)

