import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from matching import match_key


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY,
  shop TEXT NOT NULL,
  external_id TEXT NOT NULL,
  name TEXT, match_name TEXT, game TEXT, url TEXT,
  price REAL, in_stock INTEGER, is_preorder INTEGER, orderable INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT, last_seen TEXT,
  UNIQUE(shop, external_id)
);
CREATE TABLE IF NOT EXISTS price_history (
  listing_id INTEGER, ts TEXT, price REAL, in_stock INTEGER
);
CREATE TABLE IF NOT EXISTS product_baselines (
  match_key TEXT PRIMARY KEY,
  price REAL NOT NULL,
  added_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scrape_alert_state (
  shop TEXT PRIMARY KEY,
  stock_drop_active INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS product_favorites (
  match_key TEXT PRIMARY KEY,
  added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

POSTGRES_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS listings (
      id BIGSERIAL PRIMARY KEY,
      shop TEXT NOT NULL,
      external_id TEXT NOT NULL,
      name TEXT, match_name TEXT, game TEXT, url TEXT,
      price DOUBLE PRECISION, in_stock INTEGER, is_preorder INTEGER,
      orderable INTEGER NOT NULL DEFAULT 0,
      first_seen TEXT, last_seen TEXT,
      UNIQUE(shop, external_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS price_history (
      listing_id BIGINT, ts TEXT, price DOUBLE PRECISION, in_stock INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_baselines (
      match_key TEXT PRIMARY KEY,
      price DOUBLE PRECISION NOT NULL,
      added_date TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scrape_alert_state (
      shop TEXT PRIMARY KEY,
      stock_drop_active INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_favorites (
      match_key TEXT PRIMARY KEY,
      added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


class DatabaseConnection:
    """Small adapter for the shared qmark SQL used by SQLite and psycopg."""

    def __init__(self, connection, backend):
        self.connection = connection
        self.backend = backend

    def execute(self, sql, params=()):
        if self.backend == "postgres":
            sql = sql.replace("?", "%s")
        return self.connection.execute(sql, params)

    def executemany(self, sql, rows):
        if self.backend == "postgres":
            sql = sql.replace("?", "%s")
        cursor = self.connection.cursor()
        cursor.executemany(sql, rows)
        return cursor

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def connect_sqlite(path="tcg.db"):
    conn = sqlite3.connect(str(path), timeout=10)
    conn.executescript(SQLITE_SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(listings)")}
    if "match_name" not in columns:
        conn.execute("ALTER TABLE listings ADD COLUMN match_name TEXT")
    if "game" not in columns:
        conn.execute("ALTER TABLE listings ADD COLUMN game TEXT")
    if "orderable" not in columns:
        conn.execute(
            "ALTER TABLE listings ADD COLUMN orderable INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute("UPDATE listings SET orderable=COALESCE(in_stock, 0)")
    conn.commit()
    return DatabaseConnection(conn, "sqlite")


def _open_postgres(database_url):
    if not database_url:
        raise ValueError("Nedostaje DATABASE_URL za PostgreSQL.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Za PostgreSQL instaliraj pakete iz requirements.txt."
        ) from exc

    return psycopg.connect(
        database_url,
        connect_timeout=15,
        sslmode="require",
    )


def initialize_postgres(database_url):
    """Create or upgrade the PostgreSQL schema; intended for setup/migration only."""
    conn = _open_postgres(database_url)
    try:
        for statement in POSTGRES_SCHEMA:
            conn.execute(statement)

        columns = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'listings'"
            ).fetchall()
        }
        if "match_name" not in columns:
            conn.execute("ALTER TABLE listings ADD COLUMN match_name TEXT")
        if "game" not in columns:
            conn.execute("ALTER TABLE listings ADD COLUMN game TEXT")
        if "orderable" not in columns:
            conn.execute(
                "ALTER TABLE listings ADD COLUMN orderable INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute("UPDATE listings SET orderable=COALESCE(in_stock, 0)")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    return DatabaseConnection(conn, "postgres")


def connect_postgres(database_url):
    """Open PostgreSQL without running schema checks on ordinary app queries."""
    return DatabaseConnection(_open_postgres(database_url), "postgres")


def connect(path="tcg.db", database_url=None):
    """Use Supabase when DATABASE_URL is configured; otherwise use local SQLite."""
    url = database_url or os.getenv("DATABASE_URL")
    if url:
        return connect_postgres(url)
    return connect_sqlite(path)


def is_empty(conn, shop):
    n = conn.execute("SELECT COUNT(*) FROM listings WHERE shop=?", (shop,)).fetchone()[0]
    return n == 0


def apply_and_diff(conn, shop, items, seed=False):
    now = datetime.now(timezone.utc).isoformat()
    events = []
    for it in items:
        stock, pre = int(it["in_stock"]), int(it["is_preorder"])
        orderable = int(it.get("orderable", it["in_stock"]))
        match_name = it.get("match_name") or it["name"]
        game = it.get("game")
        row = conn.execute(
            "SELECT id, price, in_stock, game, orderable FROM listings WHERE shop=? AND external_id=?",
            (shop, it["external_id"]),
        ).fetchone()
        if row is None:
            insert_sql = (
                "INSERT INTO listings (shop, external_id, name, match_name, game, url, price, in_stock, "
                "is_preorder, orderable, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            )
            values = (
                shop, it["external_id"], it["name"], match_name, game, it["url"], it["price"],
                stock, pre, orderable, now, now,
            )
            if conn.backend == "postgres":
                lid = conn.execute(insert_sql + " RETURNING id", values).fetchone()[0]
            else:
                lid = conn.execute(insert_sql, values).lastrowid
            conn.execute(
                "INSERT INTO price_history VALUES (?,?,?,?)",
                (lid, now, it["price"], stock),
            )
            if orderable and not seed:
                event_type = "PREORDER_AVAILABLE" if pre and not stock else "NEW"
                events.append({"type": event_type, **it})
        else:
            lid, old_price, old_stock, old_game, old_orderable = row
            game = game or old_game
            if stock and not old_stock:
                events.append({"type": "RESTOCK", **it})
            elif pre and orderable and not old_orderable:
                events.append({"type": "PREORDER_AVAILABLE", **it})
            elif stock and old_price and it["price"] <= old_price * 0.95:
                events.append({"type": "PRICE_DROP", "old_price": old_price, **it})
            if it["price"] != old_price or stock != old_stock or orderable != old_orderable:
                conn.execute(
                    "INSERT INTO price_history VALUES (?,?,?,?)",
                    (lid, now, it["price"], stock),
                )
            conn.execute(
                "UPDATE listings SET name=?, match_name=?, game=?, url=?, price=?, in_stock=?, is_preorder=?, orderable=?, "
                "last_seen=? WHERE id=?",
                (it["name"], match_name, game, it["url"], it["price"], stock, pre, orderable, now, lid),
            )
    conn.commit()
    return events


def first_seen_map(conn, shop):
    rows = conn.execute(
        "SELECT external_id, first_seen FROM listings WHERE shop=?", (shop,)
    ).fetchall()
    return dict(rows)


def mark_missing(conn, shop, items):
    seen = {it["external_id"] for it in items}
    rows = conn.execute(
        "SELECT id, external_id FROM listings WHERE shop=? AND (in_stock=1 OR orderable=1)",
        (shop,),
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for lid, ext in rows:
        if ext not in seen:
            conn.execute("UPDATE listings SET in_stock=0, orderable=0 WHERE id=?", (lid,))
            conn.execute(
                "INSERT INTO price_history VALUES (?,?,?,?)",
                (lid, now, None, 0),
            )
            n += 1
    conn.commit()
    return n


def count_in_stock(conn, shop):
    return conn.execute(
        "SELECT COUNT(*) FROM listings WHERE shop=? AND in_stock=1", (shop,)
    ).fetchone()[0]


def stock_drop_alert_is_active(conn, shop):
    row = conn.execute(
        "SELECT stock_drop_active FROM scrape_alert_state WHERE shop=?", (shop,)
    ).fetchone()
    return bool(row and row[0])


def set_stock_drop_alert_active(conn, shop, active):
    conn.execute(
        "INSERT INTO scrape_alert_state (shop, stock_drop_active) VALUES (?, ?) "
        "ON CONFLICT(shop) DO UPDATE SET stock_drop_active=excluded.stock_drop_active",
        (shop, int(active)),
    )
    conn.commit()


def capture_product_baselines(conn, include_unavailable_preorders=()):
    rows = conn.execute("""
        SELECT l.shop, l.name, l.match_name, l.is_preorder, l.in_stock, l.orderable, l.first_seen,
               (SELECT ph.price FROM price_history ph
                WHERE ph.listing_id = l.id ORDER BY ph.ts LIMIT 1)
        FROM listings l
    """).fetchall()

    groups = defaultdict(list)
    allowed_preorders = set(include_unavailable_preorders)
    for shop, name, match_name, is_preorder, in_stock, orderable, first_seen, first_price in rows:
        if not first_seen or first_price is None:
            continue
        if not in_stock and not orderable and not (shop in allowed_preorders and is_preorder):
            continue
        key = match_key(match_name or name or "")
        if not key:
            continue
        try:
            added_date = datetime.fromisoformat(
                first_seen.replace("Z", "+00:00")
            ).astimezone().date().isoformat()
        except ValueError:
            added_date = first_seen[:10]
        groups[key].append((added_date, float(first_price)))

    for key, offers in groups.items():
        first_date = min(date for date, _ in offers)
        first_day_prices = [price for date, price in offers if date == first_date]
        conn.execute(
            "INSERT INTO product_baselines (match_key, price, added_date) "
            "VALUES (?, ?, ?) ON CONFLICT(match_key) DO NOTHING",
            (key, min(first_day_prices), first_date),
        )
    conn.commit()
