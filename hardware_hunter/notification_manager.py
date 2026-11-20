from __future__ import annotations

from hardware_hunter.models import Offer


def format_offer(offer: Offer, score: int, risk: str, reference: float | None = None) -> str:
    savings = max(0, reference - offer.total_price) if reference else 0
    discount = savings / reference * 100 if reference else 0
    lines = ["🔥 ACHADINHO DETECTADO", "", f"Produto: {offer.title}", f"Preço: R$ {offer.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")]
    if offer.shipping is None: lines.append("Frete: não informado")
    else: lines.append(f"Frete: R$ {offer.shipping:.2f}".replace(".", ","))
    if reference:
        lines += [f"Referência observada: R$ {reference:.2f}".replace(".", ","), f"Economia estimada: R$ {savings:.2f} ({discount:.0f}%)".replace(".", ",")]
    lines += [f"Hunter Score: {score}/100", f"Marketplace: {offer.marketplace}", f"Condição: {offer.condition or 'não informada'}", f"Risco: {risk}", f"Detectado pelo sistema: {offer.first_seen_at[:16]}", "A data de detecção não representa necessariamente a publicação do anúncio.", f"Link: {offer.url}", "Confira o anúncio e mantenha o pagamento dentro da plataforma."]
    return "\n".join(lines)

