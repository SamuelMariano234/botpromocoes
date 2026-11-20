from __future__ import annotations

from hardware_hunter.database import Database
from hardware_hunter.hunter_score import calculate_score
from hardware_hunter.models import Offer


def process(db: Database, offer: Offer, reference_price: float | None = None):
    hist = db.price_stats(offer.title)
    score = calculate_score(offer, reference_price, hist["median"] if hist and hist["count"] >= 3 else None)
    offer_id, is_new, dropped = db.save_offer(offer, score.value, score.risk, score.explanation)
    return offer_id, score, is_new, dropped

