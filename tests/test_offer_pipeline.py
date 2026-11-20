import tempfile
import unittest
from pathlib import Path

from hardware_hunter.database import Database
from hardware_hunter.offer_pipeline import analyze_message


class OfferPipelineTests(unittest.TestCase):
    def test_qualified_offer_is_approved(self):
        result = analyze_message("RTX 4060 8GB nova\nR$ 1.899,90\nhttps://loja.example/produto", True)
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["category"], "gpu")
        self.assertEqual(result["price"], 1899.90)

    def test_missing_link_goes_to_review_and_max_price_rejects(self):
        missing = analyze_message("SSD NVMe 1TB R$ 400,00", False)
        self.assertEqual(missing["decision"], "review")
        over = analyze_message("SSD NVMe 1TB R$ 900,00 https://shop.example/ssd", False, max_price=500)
        self.assertEqual(over["decision"], "rejected")

    def test_duplicate_message_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "db.sqlite3")
            db.initialize()
            row = {"source_chat_id": "-10042", "source_message_id": 9, "source_title": "origem",
                   "text": "RTX 4060 R$ 1000 https://example.com", "links": "https://example.com",
                   "media_path": None, "price": 1000.0, "category": "gpu", "hunter_score": 80,
                   "risk_level": "baixo", "decision": "approved", "reason": "test", "received_at": "2026-01-01T00:00:00+00:00"}
            self.assertTrue(db.save_collected(row))
            self.assertFalse(db.save_collected(row))


if __name__ == "__main__":
    unittest.main()
