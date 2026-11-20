from __future__ import annotations

import re
import unicodedata

DEFAULT_EXCLUSIONS = ("caixa vazia", "somente caixa", "manual", "adesivo", "para reparo", "defeito",
                      "não funciona", "nao funciona", "procuro", "troco", "troca", "leia o anúncio")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def search_variants(query: str) -> list[str]:
    q = query.strip()
    if not q: return []
    variants = [q]
    compact = re.sub(r"[- ]+", "", q)
    if compact.lower() != q.lower(): variants.append(compact)
    spaced = re.sub(r"[-]+", " ", q)
    if spaced.lower() != q.lower(): variants.append(spaced)
    variants += [f"{q} usado", f"{q} 8GB"] if any(x in q.lower() for x in ("rtx", "rx ")) else [f"{q} usado"]
    return list(dict.fromkeys(variants))


def matches_offer(title: str, query: str, exclusions: tuple[str, ...] = DEFAULT_EXCLUSIONS) -> bool:
    nt, nq = normalize(title), normalize(query)
    if not nt or not nq or any(normalize(word) in nt for word in exclusions): return False
    tokens = nq.split()
    # Require all meaningful model tokens to avoid broad cross-model matches.
    return all(token in nt.split() for token in tokens)

