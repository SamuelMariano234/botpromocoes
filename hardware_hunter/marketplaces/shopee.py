"""Shopee adapter placeholder; requires an authorized partner integration."""
class Shopee:
    name = "shopee"
    enabled = False
    limitation = "Busca de produtos requer integração/credenciais de parceiro; endpoints privados e scraping não são utilizados."

    async def search(self, query: str, limit: int = 20):
        return []

