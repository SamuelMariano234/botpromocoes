from __future__ import annotations

from typing import Protocol

from hardware_hunter.models import Offer


class Marketplace(Protocol):
    name: str
    async def search(self, query: str, limit: int = 20) -> list[Offer]: ...

