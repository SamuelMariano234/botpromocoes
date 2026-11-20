from __future__ import annotations

from hardware_hunter.database import Database


def summarize(db: Database, query: str):
    """Summarize currently observed listings; does not fabricate historical coverage."""
    return db.price_stats(query)

