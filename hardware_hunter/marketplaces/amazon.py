"""Amazon BR adapter placeholder. No authorized public product search API is configured."""
class Amazon:
    name = "amazon"
    enabled = False
    limitation = "A Product Advertising API exige conta/credenciais e elegibilidade; scraping não é utilizado."

    async def search(self, query: str, limit: int = 20):
        return []

