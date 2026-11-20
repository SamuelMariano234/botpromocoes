from __future__ import annotations

import logging

import httpx

from hardware_hunter.models import Offer

log = logging.getLogger(__name__)
API = "https://api.mercadolibre.com/sites/MLB/search"


class MercadoLivre:
    """Uses Mercado Livre's public catalog search endpoint; no scraping or CAPTCHA bypass."""
    name = "mercado_livre"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(self, query: str, limit: int = 20) -> list[Offer]:
        async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "HardwareHunterBR/1.0 (personal deal research)"}) as client:
            response = await client.get(API, params={"q": query, "limit": min(max(limit, 1), 50)})
            response.raise_for_status()
            payload = response.json()
        offers = []
        for item in payload.get("results", []):
            shipping = item.get("shipping") or {}
            cost = shipping.get("cost")
            seller = item.get("seller") or {}
            seller_id = seller.get("id")
            offers.append(Offer(
                marketplace=self.name, title=item.get("title", "(sem título)"),
                price=float(item.get("price") or 0), url=item.get("permalink", ""),
                item_id=str(item.get("id", "")), condition=item.get("condition"),
                shipping=float(cost) if cost is not None else None,
                seller=str(seller_id) if seller_id else None,
                seller_reputation=None, published_at=item.get("date_created"),
            ))
        return [offer for offer in offers if offer.item_id and offer.url and offer.price > 0]

