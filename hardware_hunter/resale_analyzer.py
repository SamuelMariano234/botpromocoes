from __future__ import annotations


def estimate_resale(buy_price: float, observed_prices: list[float], fee_rate: float = 0.13,
                    shipping_cost: float = 0, maintenance_cost: float = 0) -> dict[str, float | str] | None:
    if len(observed_prices) < 3 or buy_price <= 0: return None
    resale = sorted(observed_prices)[len(observed_prices)//2]
    net = resale * (1-fee_rate) - shipping_cost - maintenance_cost - buy_price
    return {"resale_estimate": resale, "net_profit_estimate": net,
            "margin_percent": net / buy_price * 100, "confidence": "baixa; amostra pequena"}

