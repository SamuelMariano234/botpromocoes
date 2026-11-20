from __future__ import annotations

from dataclasses import dataclass

from hardware_hunter.models import Offer


@dataclass
class Risk:
    level: str
    penalty: int
    reasons: list[str]


def analyze_risk(offer: Offer, reference_price: float | None = None) -> Risk:
    reasons: list[str] = []
    penalty = 0
    text = f"{offer.title} {offer.description or ''}".lower()
    if reference_price and offer.price < reference_price * 0.55:
        penalty += 28; reasons.append("Preço muito abaixo da referência; confirme a oferta com cuidado")
    elif reference_price and offer.price < reference_price * 0.75:
        penalty += 10; reasons.append("Preço abaixo da referência")
    if not offer.seller_reputation:
        penalty += 8; reasons.append("Reputação do vendedor não disponível")
    if any(w in text for w in ("defeito", "para conserto", "não funciona", "nao funciona", "sem teste")):
        penalty += 30; reasons.append("Anúncio menciona defeito ou falta de teste")
    if any(w in text for w in ("pix por fora", "fora da plataforma", "whatsapp para pagar")):
        penalty += 35; reasons.append("Possível solicitação de pagamento fora da plataforma")
    if len(offer.title.strip()) < 12:
        penalty += 8; reasons.append("Descrição curta; informações insuficientes")
    if not reasons:
        return Risk("informações insuficientes", 5, ["Dados do anúncio limitados; verifique condição e vendedor"])
    if penalty >= 30: level = "elevado"
    elif penalty >= 12: level = "moderado"
    else: level = "baixo"
    return Risk(level, min(45, penalty), reasons)

