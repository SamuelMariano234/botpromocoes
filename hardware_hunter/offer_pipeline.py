from __future__ import annotations

import re
from datetime import datetime, timezone


PRICE_RE = re.compile(r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{1,2})?|[0-9]+(?:,[0-9]{1,2})?)", re.I)
URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
CATEGORIES = {
    "gpu": ("gpu", "placa de vídeo", "placa de video", "rtx", "gtx", "radeon", "rx 6", "rx 7"),
    "cpu": ("ryzen", "core i", "i5-", "i7-", "processador"),
    "ram": ("memória ram", "memoria ram", "ddr4", "ddr5"),
    "ssd": ("ssd", "nvme", "m.2", "sata"),
    "fonte": ("fonte atx", "fonte 550", "fonte 650", "fonte 750", "80 plus"),
    "monitor": ("monitor", "144hz", "165hz", "240hz"),
    "periférico": ("mouse", "teclado", "headset", "headphone"),
}
EXCLUSIONS = ("caixa vazia", "somente caixa", "para conserto", "não funciona", "nao funciona", "procuro", "troco", "troca", "pix por fora")


def analyze_message(text: str, has_media: bool, min_score: int = 70, max_price: float | None = None) -> dict:
    price_match = PRICE_RE.search(text)
    price = None
    if price_match:
        try: price = float(price_match.group(1).replace(".", "").replace(",", "."))
        except ValueError: pass
    links = [u.rstrip(".,)") for u in URL_RE.findall(text)]
    lowered = text.casefold()
    category = next((name for name, terms in CATEGORIES.items() if any(term in lowered for term in terms)), "outros")
    score = 20
    reasons = []
    if category != "outros": score += 20; reasons.append(f"categoria reconhecida: {category}")
    if price is not None: score += 20; reasons.append("preço explícito")
    if links: score += 20; reasons.append("link detectado")
    if len(text.strip()) >= 40: score += 10; reasons.append("texto com contexto")
    if has_media: score += 5; reasons.append("mídia disponível")
    risk = "baixo"
    if any(term in lowered for term in EXCLUSIONS):
        risk = "elevado"; score -= 35; reasons.append("termo de risco/exclusão detectado")
    elif "sem garantia" in lowered or "defeito" in lowered:
        risk = "moderado"; score -= 20; reasons.append("condição/garantia requer revisão")
    if price is None: reasons.append("sem preço: encaminhado para revisão")
    if not links: reasons.append("sem link: encaminhado para revisão")
    if max_price is not None and price is not None and price > max_price:
        return {"price": price, "links": links, "category": category, "score": max(0, score), "risk": risk,
                "decision": "rejected", "reason": f"Preço R$ {price:.2f} acima do limite R$ {max_price:.2f}; " + "; ".join(reasons)}
    if price is None or not links or risk == "elevado": decision = "review"
    else: decision = "approved" if score >= min_score else "rejected"
    return {"price": price, "links": links, "category": category, "score": max(0, min(100, score)),
            "risk": risk, "decision": decision, "reason": "; ".join(reasons) or "relevância não confirmada"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
