from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hardware_hunter.models import Offer


SCHEMA_VERSION = 2


class ClosingConnection(sqlite3.Connection):
    """SQLite context manager that also closes the handle on Windows."""
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=20, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS watchlist (
              id INTEGER PRIMARY KEY, query TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'outros',
              max_price REAL, ideal_price REAL, min_score INTEGER NOT NULL DEFAULT 60,
              condition TEXT, marketplaces TEXT NOT NULL DEFAULT '["mercado_livre"]',
              active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(query COLLATE NOCASE));
            CREATE TABLE IF NOT EXISTS offers (
              id INTEGER PRIMARY KEY, marketplace TEXT NOT NULL, item_id TEXT NOT NULL,
              title TEXT NOT NULL, price REAL NOT NULL, shipping REAL, condition TEXT,
              seller TEXT, seller_reputation TEXT, url TEXT NOT NULL, product_key TEXT,
              first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, published_at TEXT,
              status TEXT NOT NULL DEFAULT 'active', hunter_score INTEGER, risk_level TEXT,
              score_explanation TEXT, UNIQUE(marketplace, item_id));
            CREATE TABLE IF NOT EXISTS price_history (
              id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
              price REAL NOT NULL, shipping REAL, observed_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_history_offer_time ON price_history(offer_id, observed_at);
            CREATE TABLE IF NOT EXISTS notifications (
              id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
              user_id INTEGER NOT NULL, sent_price REAL NOT NULL, sent_at TEXT NOT NULL,
              UNIQUE(offer_id, user_id));
            CREATE TABLE IF NOT EXISTS favorites (
              user_id INTEGER NOT NULL, offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, offer_id));
            CREATE TABLE IF NOT EXISTS settings (
              user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
              PRIMARY KEY(user_id, key));
            CREATE TABLE IF NOT EXISTS source_groups (
              chat_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS monitored_groups (
              chat_ref TEXT PRIMARY KEY, chat_id TEXT, title TEXT, added_by INTEGER NOT NULL,
              active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS collected_messages (
              id INTEGER PRIMARY KEY, source_chat_id TEXT NOT NULL, source_message_id INTEGER NOT NULL,
              source_title TEXT NOT NULL, text TEXT NOT NULL, links TEXT NOT NULL DEFAULT '', media_path TEXT,
              price REAL, category TEXT NOT NULL DEFAULT 'outros', hunter_score INTEGER NOT NULL DEFAULT 0,
              risk_level TEXT NOT NULL DEFAULT 'informações insuficientes', decision TEXT NOT NULL DEFAULT 'review',
              reason TEXT NOT NULL DEFAULT '', received_at TEXT NOT NULL, published_at TEXT,
              UNIQUE(source_chat_id,source_message_id));
            CREATE INDEX IF NOT EXISTS idx_collected_decision ON collected_messages(decision,received_at);
            CREATE TABLE IF NOT EXISTS search_log (
              id INTEGER PRIMARY KEY, query TEXT NOT NULL, searched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              result_count INTEGER NOT NULL DEFAULT 0);
            """)
            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))

    def add_watch(self, query: str, category: str = "outros", max_price: float | None = None,
                  ideal_price: float | None = None) -> bool:
        with self.connect() as db:
            cur = db.execute("INSERT OR IGNORE INTO watchlist(query,category,max_price,ideal_price) VALUES(?,?,?,?)",
                              (query.strip(), category, max_price, ideal_price))
            return cur.rowcount > 0

    def remove_watch(self, query: str) -> bool:
        with self.connect() as db:
            cur = db.execute("DELETE FROM watchlist WHERE query=? COLLATE NOCASE", (query.strip(),))
            return cur.rowcount > 0

    def watches(self, active_only: bool = False) -> list[dict[str, Any]]:
        with self.connect() as db:
            sql = "SELECT * FROM watchlist" + (" WHERE active=1" if active_only else "") + " ORDER BY query"
            return [dict(row) for row in db.execute(sql)]

    def save_offer(self, offer: Offer, score: int, risk: str, explanation: list[str]) -> tuple[int, bool, bool]:
        """Returns (id, is_new, price_dropped)."""
        with self.connect() as db:
            old = db.execute("SELECT id,price,first_seen_at FROM offers WHERE marketplace=? AND item_id=?",
                             (offer.marketplace, offer.item_id)).fetchone()
            is_new = old is None
            dropped = bool(old and offer.price < old["price"] * 0.95)
            db.execute("""INSERT INTO offers(marketplace,item_id,title,price,shipping,condition,seller,
                seller_reputation,url,product_key,first_seen_at,last_seen_at,published_at,hunter_score,
                risk_level,score_explanation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(marketplace,item_id) DO UPDATE SET title=excluded.title,price=excluded.price,
                shipping=excluded.shipping,condition=excluded.condition,seller=excluded.seller,
                seller_reputation=excluded.seller_reputation,url=excluded.url,last_seen_at=excluded.last_seen_at,
                published_at=COALESCE(excluded.published_at,offers.published_at),hunter_score=excluded.hunter_score,
                risk_level=excluded.risk_level,score_explanation=excluded.score_explanation""",
                       (offer.marketplace, offer.item_id, offer.title, offer.price, offer.shipping,
                        offer.condition, offer.seller, offer.seller_reputation, offer.url, offer.product_key,
                        offer.first_seen_at if is_new else old["first_seen_at"], offer.first_seen_at,
                        offer.published_at, score, risk, json.dumps(explanation, ensure_ascii=False)))
            row = db.execute("SELECT id FROM offers WHERE marketplace=? AND item_id=?",
                             (offer.marketplace, offer.item_id)).fetchone()
            oid = int(row["id"])
            db.execute("INSERT INTO price_history(offer_id,price,shipping,observed_at) VALUES(?,?,?,?)",
                       (oid, offer.price, offer.shipping, offer.first_seen_at))
            return oid, is_new, dropped

    def offers(self, min_score: int = 0, limit: int = 20, category_query: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            sql = "SELECT * FROM offers WHERE hunter_score>=?"
            args: list[Any] = [min_score]
            if category_query:
                sql += " AND title LIKE ?"; args.append(f"%{category_query}%")
            sql += " ORDER BY hunter_score DESC, last_seen_at DESC LIMIT ?"; args.append(limit)
            return [dict(row) for row in db.execute(sql, args)]

    def should_notify(self, offer_id: int, user_id: int, price: float) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT sent_price FROM notifications WHERE offer_id=? AND user_id=?",
                             (offer_id, user_id)).fetchone()
            if row is None:
                return True
            return price <= row["sent_price"] * 0.95

    def mark_notified(self, offer_id: int, user_id: int, price: float, sent_at: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO notifications(offer_id,user_id,sent_price,sent_at) VALUES(?,?,?,?) "
                       "ON CONFLICT(offer_id,user_id) DO UPDATE SET sent_price=excluded.sent_price,sent_at=excluded.sent_at",
                       (offer_id, user_id, price, sent_at))

    def favorites(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT o.* FROM offers o JOIN favorites f ON f.offer_id=o.id WHERE f.user_id=? ORDER BY f.created_at DESC", (user_id,))]

    def toggle_favorite(self, user_id: int, offer_id: int) -> bool:
        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM favorites WHERE user_id=? AND offer_id=?", (user_id, offer_id)).fetchone()
            if exists:
                db.execute("DELETE FROM favorites WHERE user_id=? AND offer_id=?", (user_id, offer_id)); return False
            db.execute("INSERT OR IGNORE INTO favorites(user_id,offer_id) VALUES(?,?)", (user_id, offer_id)); return True

    def log_search(self, query: str, count: int) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO search_log(query,result_count) VALUES(?,?)", (query, count))

    def set_setting(self, user_id: int, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO settings(user_id,key,value) VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value",
                       (user_id, key, value))

    def get_setting(self, user_id: int, key: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE user_id=? AND key=?", (user_id, key)).fetchone()
            return row["value"] if row else None

    def add_source_group(self, user_id: int, chat_id: int) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO source_groups(chat_id,user_id) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET user_id=excluded.user_id",
                       (str(chat_id), user_id))

    def remove_source_group(self, user_id: int, chat_id: int) -> bool:
        with self.connect() as db:
            cur = db.execute("DELETE FROM source_groups WHERE chat_id=? AND user_id=?", (str(chat_id), user_id))
            return cur.rowcount > 0

    def source_owner(self, chat_id: int) -> int | None:
        with self.connect() as db:
            row = db.execute("SELECT user_id FROM source_groups WHERE chat_id=?", (str(chat_id),)).fetchone()
            return int(row["user_id"]) if row else None

    def add_monitored_group(self, chat_ref: str, added_by: int) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO monitored_groups(chat_ref,added_by) VALUES(?,?) ON CONFLICT(chat_ref) DO UPDATE SET added_by=excluded.added_by,active=1",
                       (chat_ref.strip(), added_by))

    def remove_monitored_group(self, chat_ref: str) -> bool:
        with self.connect() as db:
            cur = db.execute("DELETE FROM monitored_groups WHERE chat_ref=?", (chat_ref.strip(),))
            return cur.rowcount > 0

    def set_group_active(self, chat_ref: str, active: bool) -> bool:
        with self.connect() as db:
            cur = db.execute("UPDATE monitored_groups SET active=? WHERE chat_ref=?", (int(active), chat_ref.strip()))
            return cur.rowcount > 0

    def monitored_groups(self, active_only: bool = False) -> list[dict[str, Any]]:
        with self.connect() as db:
            sql = "SELECT * FROM monitored_groups" + (" WHERE active=1" if active_only else "") + " ORDER BY chat_ref"
            return [dict(row) for row in db.execute(sql)]

    def save_collected(self, row: dict[str, Any]) -> bool:
        with self.connect() as db:
            cur = db.execute("""INSERT OR IGNORE INTO collected_messages(source_chat_id,source_message_id,source_title,text,links,media_path,price,category,hunter_score,risk_level,decision,reason,received_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (row["source_chat_id"], row["source_message_id"], row["source_title"], row["text"], row["links"], row.get("media_path"), row.get("price"), row["category"], row["hunter_score"], row["risk_level"], row["decision"], row["reason"], row["received_at"]))
            return cur.rowcount > 0

    def collected(self, decision: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as db:
            if decision:
                rows = db.execute("SELECT * FROM collected_messages WHERE decision=? ORDER BY received_at DESC LIMIT ?", (decision, limit))
            else:
                rows = db.execute("SELECT * FROM collected_messages ORDER BY received_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in rows]

    def pending_collected(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""SELECT c.*,g.added_by FROM collected_messages c
              JOIN monitored_groups g ON g.chat_id=c.source_chat_id
              WHERE c.decision='approved' AND g.active=1 ORDER BY c.received_at LIMIT ?""", (limit,))
            return [dict(r) for r in rows]

    def collected_stats(self) -> dict[str, int]:
        with self.connect() as db:
            data = {r["decision"]: r["n"] for r in db.execute("SELECT decision,COUNT(*) n FROM collected_messages GROUP BY decision")}
            data["total"] = sum(data.values())
            return data

    def mark_collected_published(self, row_id: int, published_at: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE collected_messages SET decision='published',published_at=? WHERE id=?", (published_at, row_id))

    def set_collected_decision(self, row_id: int, decision: str) -> bool:
        with self.connect() as db:
            cur = db.execute("UPDATE collected_messages SET decision=? WHERE id=?", (decision, row_id))
            return cur.rowcount > 0

    def clear_offers(self) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM offers")

    def price_stats(self, query: str) -> dict[str, float | int] | None:
        with self.connect() as db:
            rows = [r[0] for r in db.execute("SELECT price FROM offers WHERE title LIKE ?", (f"%{query}%",))]
        if not rows: return None
        ordered = sorted(rows); n = len(ordered)
        return {"count": n, "min": min(rows), "max": max(rows), "mean": sum(rows)/n,
                "median": ordered[n//2] if n % 2 else (ordered[n//2-1]+ordered[n//2])/2}

