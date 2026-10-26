"""Copy the local tcg.db into an empty PostgreSQL database."""

import os
from pathlib import Path

import db


TABLE_COLUMNS = {
    "listings": (
        "id", "shop", "external_id", "name", "match_name", "game", "url",
        "price", "in_stock", "is_preorder", "orderable", "first_seen", "last_seen",
    ),
    "price_history": ("listing_id", "ts", "price", "in_stock"),
    "product_baselines": ("match_key", "price", "added_date"),
    "scrape_alert_state": ("shop", "stock_drop_active"),
    "product_favorites": ("match_key", "added_at"),
}


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "Postavi DATABASE_URL u okruženju prije pokretanja migracije."
        )

    sqlite_path = Path(__file__).with_name("tcg.db")
    if not sqlite_path.is_file():
        raise SystemExit(f"Nije pronađena lokalna baza: {sqlite_path}")

    source = db.connect_sqlite(sqlite_path)
    target = db.initialize_postgres(database_url)
    try:
        source_counts = {
            table: source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLE_COLUMNS
        }

        with target as destination:
            destination_counts = {
                table: destination.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in TABLE_COLUMNS
            }
            populated = [
                table for table, count in destination_counts.items() if count
            ]
            if populated:
                raise RuntimeError(
                    "Supabase baza nije prazna; radi sigurnosti nisam kopirao podatke. "
                    "Postojeći zapisi: " + ", ".join(populated)
                )

            for table, columns in TABLE_COLUMNS.items():
                column_list = ", ".join(columns)
                rows = source.execute(
                    f"SELECT {column_list} FROM {table}"
                ).fetchall()
                if rows:
                    placeholders = ", ".join("?" for _ in columns)
                    destination.executemany(
                        f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",
                        rows,
                    )

                copied = destination.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                if copied != source_counts[table]:
                    raise RuntimeError(
                        f"Provjera nije prošla za {table}: lokalno "
                        f"{source_counts[table]}, cloud {copied}."
                    )

            destination.execute("""
                SELECT setval(
                    pg_get_serial_sequence('listings', 'id'),
                    COALESCE((SELECT MAX(id) FROM listings), 1),
                    EXISTS(SELECT 1 FROM listings)
                )
            """)
    finally:
        source.close()

    print("Prijenos je dovršen i broj redaka je provjeren:")
    for table, count in source_counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
