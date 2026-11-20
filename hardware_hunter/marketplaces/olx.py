"""OLX adapter placeholder; no authorized search feed/API configured."""
class OLX:
    name = "olx"
    enabled = False
    limitation = "Não há integração de busca autorizada configurada. Acesso automatizado não permitido não será tentado."

    async def search(self, query: str, limit: int = 20):
        return []

