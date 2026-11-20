import tempfile
import unittest
from pathlib import Path

from hardware_hunter.database import Database
from hardware_hunter.filters import accepts
from hardware_hunter.hunter_score import calculate_score
from hardware_hunter.models import Offer
from hardware_hunter.product_matcher import search_variants
from hardware_hunter.risk_analyzer import analyze_risk


class CoreTests(unittest.TestCase):
    def sample(self, **changes):
        data = dict(marketplace="mercado_livre", title="Placa de vídeo RTX 3060 12GB usada", price=800,
                    url="https://example.invalid/item", item_id="MLB123", condition="used",
                    seller="123", seller_reputation="seller_reputation")
        data.update(changes)
        return Offer(**data)

    def test_search_variants_and_filter(self):
        self.assertIn("RTX3060", search_variants("RTX 3060"))
        self.assertTrue(accepts(self.sample(), "RTX 3060"))
        self.assertFalse(accepts(self.sample(title="Caixa vazia RTX 3060"), "RTX 3060"))
        self.assertFalse(accepts(self.sample(price=1100), "RTX 3060", max_price=1000))

    def test_risk_and_score_are_conservative(self):
        risky = self.sample(price=300, seller_reputation=None, description="Pix por fora")
        result = analyze_risk(risky, 900)
        self.assertEqual(result.level, "elevado")
        score = calculate_score(risky, 900)
        self.assertLess(score.value, 60)

    def test_watchlist_and_database_dedup(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.db"); db.initialize()
            self.assertTrue(db.add_watch("RTX 3060", max_price=1000))
            self.assertFalse(db.add_watch("RTX 3060"))
            offer = self.sample()
            oid, is_new, dropped = db.save_offer(offer, 70, "moderado", ["test"])
            self.assertTrue(is_new); self.assertFalse(dropped)
            updated = self.sample(price=750)
            oid2, is_new2, dropped2 = db.save_offer(updated, 75, "baixo", ["test"])
            self.assertEqual(oid, oid2); self.assertFalse(is_new2); self.assertTrue(dropped2)
            self.assertEqual(len(db.offers()), 1)
            self.assertTrue(db.remove_watch("RTX 3060"))


if __name__ == "__main__":
    unittest.main()
