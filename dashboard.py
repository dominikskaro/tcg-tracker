import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import yaml
from scrapers import shopify, woocommerce
from games import infer_game
import db

import pandas as pd
import streamlit as st

from matching import match_key

DB_PATH = Path(__file__).with_name("tcg.db")

st.set_page_config(page_title="TCG Tracker", layout="wide")
st.title("TCG Tracker — cijene i zalihe")
st.caption(
    "Prikazuje proizvode na zalihi, naručive SophosLab prednarudžbe i Shopify "
    "prednarudžbe koje Shopify API označi kao nedostupne. * uz cijenu označava "
    "prednarudžbu dostupnu za narudžbu."
)

if st.button("Osvježi podatke"):
    st.rerun()


def format_time(value):
    if not value:
        return "—"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime(
        "%d.%m.%Y %H:%M"
    )


with db.connect(DB_PATH) as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_favorites (
            match_key TEXT PRIMARY KEY,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    listing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(listings)")
    }
    match_name_column = "match_name" if "match_name" in listing_columns else "NULL"
    game_column = "game" if "game" in listing_columns else "NULL"
    listings = conn.execute("""
        SELECT shop, name, {match_name_column} AS match_name, price, url, is_preorder, first_seen, last_seen,
               (SELECT CASE WHEN COUNT(*) > 1 THEN MAX(ts) END
                FROM price_history
                WHERE listing_id = listings.id) AS last_change,
               in_stock, {game_column} AS game, orderable
        FROM listings
        WHERE price >= 30
    """.format(match_name_column=match_name_column, game_column=game_column)).fetchall()

    shop_updates = conn.execute("""
        SELECT shop, MAX(last_seen)
        FROM listings
        WHERE in_stock = 1 OR (shop = 'sophoslab' AND orderable = 1)
        GROUP BY shop
        ORDER BY shop
    """).fetchall()
    baseline_table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_baselines'"
    ).fetchone()
    baseline_prices = dict(conn.execute(
        "SELECT match_key, price FROM product_baselines"
    ).fetchall()) if baseline_table_exists else {}
    favorite_keys = {
        row[0] for row in conn.execute("SELECT match_key FROM product_favorites")
    }

with open(Path(__file__).with_name("shops.yaml"), encoding="utf-8") as f:
    shop_configs = yaml.safe_load(f)["shops"]
    shop_config_by_name = {shop["name"]: shop for shop in shop_configs}
    platform_by_shop = {
        shop["name"]: shop["platform"]
        for shop in shop_configs
    }


def is_excluded(shop, name):
    platform = platform_by_shop.get(shop)

    if platform == "shopify":
        return shopify.EXCLUDE.search(name) is not None

    if platform == "woocommerce":
        return woocommerce.EXCLUDE.search(name) is not None
    return False


listings = [
    row for row in listings
    if bool(row[9]) or (
        platform_by_shop.get(row[0]) == "shopify" and bool(row[5])
        and shop_config_by_name.get(row[0], {}).get("include_unavailable_preorders", False)
    ) or (
        platform_by_shop.get(row[0]) == "sophoslab" and bool(row[5]) and bool(row[11])
    )
]

listings = [
    row for row in listings
    if not is_excluded(row[0], row[1] or "")
]

groups = defaultdict(list)

for shop, name, match_name, price, url, is_preorder, first_seen, last_seen, last_change, in_stock, game, orderable in listings:
    name = name or "(bez naziva)"
    key = match_key(match_name or name) or name.casefold()
    game = game or infer_game(match_name, name)
    groups[key].append({
        "match_key": key,
        "game": game,
        "shop": shop,
        "name": name,
        "price": float(price),
        "url": url or "",
        "preorder": bool(is_preorder),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "last_change": last_change,
        "in_stock": bool(in_stock),
        "orderable": bool(orderable),
    })


col1, col2, col3 = st.columns(3)
col1.metric("Prikazanih zapisa", len(listings))
matched_groups = [
    group for group in groups.values()
    if len({row["shop"] for row in group}) >= 2
]
col2.metric("Usporedivih grupa (2+ shopa)", len(matched_groups))
single_shop_groups = [
    group for group in groups.values()
    if len({row["shop"] for row in group}) == 1
]
col3.metric("Grupa u jednom shopu", len(single_shop_groups))
st.caption(
    "Usporedbe se grupiraju prema sličnosti naziva. Provjeri nazive iz svakog shopa "
    "jer se različiti proizvodi mogu pogrešno poklopiti."
)

with st.expander("Zadnje ažurirani zapisi po shopu"):
    for shop, last_seen in shop_updates:
        st.write(f"**{shop}** — {format_time(last_seen)}")

search = st.text_input("Traži proizvod ili shop")
shop_names = sorted({row[0] for row in listings})
selected_shop = st.selectbox("Prikaži proizvode iz shopa", ["Svi shopovi"] + shop_names)
game_names = sorted({row["game"] for group in groups.values() for row in group if row["game"]})
has_unknown_game = any(not row["game"] for group in groups.values() for row in group)
game_options = ["Sve igre"] + game_names + (["Nepoznato"] if has_unknown_game else [])
selected_game = st.selectbox("Prikaži igru", game_options)
only_favorites = st.checkbox("Samo favoriti")

visible_groups = []

for group in groups.values():
    group_key = group[0]["match_key"]
    if only_favorites and group_key not in favorite_keys:
        continue

    group_games = {row["game"] for row in group if row["game"]}
    if selected_game == "Nepoznato" and group_games:
        continue
    if selected_game not in {"Sve igre", "Nepoznato"} and selected_game not in group_games:
        continue

    if selected_shop != "Svi shopovi" and not any(
        row["shop"] == selected_shop for row in group
    ):
        continue

    if search and not any(
        search.casefold() in f"{row['name']} {row['shop']}".casefold()
        for row in group
    ):
        continue

    visible_groups.append(group)

visible_groups.sort(key=lambda group: min(row["price"] for row in group))

table_rows = []

def url_with_fragment(url, fragment):
    if not url:
        return None
    return f'{url.split("#", 1)[0]}#{fragment}'


for group in visible_groups:
    cheapest = min(group, key=lambda row: row["price"])
    lowest_price = cheapest["price"]
    highest_price = max(row["price"] for row in group)
    comparable = len({row["shop"] for row in group}) >= 2
    savings_percent = (
        (highest_price - lowest_price) / highest_price * 100
        if comparable and highest_price else None
    )
    offers_by_shop = {}
    for offer in group:
        previous = offers_by_shop.get(offer["shop"])
        if previous is None or offer["price"] < previous["price"]:
            offers_by_shop[offer["shop"]] = offer
    first_seen_dates = [row["first_seen"] for row in group if row["first_seen"]]
    last_seen_dates = [row["last_seen"] for row in group if row["last_seen"]]
    first_seen = min(first_seen_dates) if first_seen_dates else None
    last_seen = max(last_seen_dates) if last_seen_dates else None
    change_dates = [row["last_change"] for row in group if row["last_change"]]
    last_change = max(change_dates) if change_dates else None

    table_row = {
        "_match_key": group[0]["match_key"],
        "Favorit": group[0]["match_key"] in favorite_keys,
        "Proizvod": cheapest["name"],
        "Najjeftiniji shop": url_with_fragment(
            cheapest["url"], f'tracker-shop={cheapest["shop"]}'
        ),
        "Najniža cijena (€)": lowest_price,
        "Cijena pri dodavanju (€)": baseline_prices.get(group[0]["match_key"]),
        "Razlika među shopovima (%)": savings_percent,
        "Dodano u bazu": format_time(first_seen),
        "Zadnja promjena cijene/zalihe": (
            format_time(last_change) if last_change else "Bez promjene"
        ),
        "Zadnji put scrapean": format_time(last_seen),
    }

    for shop in shop_names:
        offer = offers_by_shop.get(shop)
        if offer:
            price_label = f'{offer["price"]:.2f}'
            if offer["preorder"] and not offer["in_stock"]:
                price_label += "*"
            table_row[shop] = url_with_fragment(
                offer["url"], f"tracker-price={price_label}"
            )
        else:
            table_row[shop] = None

    table_rows.append(table_row)

if table_rows:
    def save_favorite_changes(group_keys):
        editor_state = st.session_state.get("offers_editor", {})
        edited_rows = editor_state.get("edited_rows", {})
        if not edited_rows:
            return
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_favorites (
                    match_key TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for row_index, changes in edited_rows.items():
                if "Favorit" not in changes:
                    continue
                group_key = group_keys[int(row_index)]
                if bool(changes["Favorit"]):
                    conn.execute(
                        "INSERT OR IGNORE INTO product_favorites (match_key) VALUES (?)",
                        (group_key,),
                    )
                else:
                    conn.execute(
                        "DELETE FROM product_favorites WHERE match_key=?",
                        (group_key,),
                    )
            conn.commit()

    column_config = {
        "Favorit": st.column_config.CheckboxColumn(
            "Favorit",
            help="Označi proizvod kao favorit.",
        ),
        "Najjeftiniji shop": st.column_config.LinkColumn(
            "Najjeftiniji shop",
            display_text=r"#tracker-shop=(.*)$",
        ),
        "Najniža cijena (€)": st.column_config.NumberColumn(format="%.2f €"),
        "Cijena pri dodavanju (€)": st.column_config.NumberColumn(format="%.2f €"),
        "Razlika među shopovima (%)": st.column_config.NumberColumn(format="%.1f%%"),
    }
    for shop in shop_names:
        column_config[shop] = st.column_config.LinkColumn(
            shop,
            display_text=r"#tracker-price=(.*)$",
        )

    table_df = pd.DataFrame(table_rows).set_index("_match_key")
    table_df.index.name = None
    st.data_editor(
        table_df,
        hide_index=True,
        width="stretch",
        column_config=column_config,
        disabled=[column for column in table_df.columns if column != "Favorit"],
        num_rows="fixed",
        key="offers_editor",
        on_change=save_favorite_changes,
        args=(list(table_df.index),),
    )
else:
    st.info("Nema proizvoda koji odgovaraju odabranom filtru.")

if visible_groups:
    with st.expander("Povijest cijena po shopu"):
        history_groups = {
            group[0]["match_key"]: group
            for group in visible_groups
        }
        history_labels = {}
        for key, group in history_groups.items():
            title = min(group, key=lambda row: row["price"])["name"]
            shop_count = len({row["shop"] for row in group})
            history_labels[key] = f"{title} ({shop_count} shopova)"

        selected_history_key = st.selectbox(
            "Odaberi proizvod",
            options=list(history_groups),
            format_func=lambda key: history_labels[key],
            key="price_history_product",
        )

        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            history_rows = conn.execute("""
                SELECT l.shop, l.name, l.match_name, ph.ts, ph.price, ph.in_stock
                FROM listings l
                JOIN price_history ph ON ph.listing_id = l.id
                WHERE ph.ts IS NOT NULL
                ORDER BY ph.ts
            """).fetchall()

        history_data = []
        for shop, name, match_name, ts, price, in_stock in history_rows:
            row_key = match_key(match_name or name or "") or (name or "").casefold()
            if row_key != selected_history_key:
                continue
            history_data.append({
                "Datum": datetime.fromisoformat(
                    ts.replace("Z", "+00:00")
                ).astimezone(),
                "Shop": shop,
                "Cijena (€)": float(price) if price is not None else None,
                "Na zalihi": "Da" if in_stock else "Ne",
            })

        if history_data:
            history_df = pd.DataFrame(history_data)
            price_chart = (
                history_df.dropna(subset=["Cijena (€)"])
                .pivot_table(
                    index="Datum",
                    columns="Shop",
                    values="Cijena (€)",
                    aggfunc="last",
                )
                .sort_index()
            )
            if not price_chart.empty:
                st.line_chart(
                    price_chart,
                    height=320,
                    y_label="Cijena (€)",
                )

            st.dataframe(
                history_df.sort_values("Datum", ascending=False),
                hide_index=True,
                width="stretch",
                column_config={
                    "Cijena (€)": st.column_config.NumberColumn(format="%.2f €"),
                },
            )
            st.caption(
                "Povijest bilježi početno stanje i promjene cijene ili zalihe; "
                "ne dodaje zapis za svaki scrape."
            )
        else:
            st.info("Za ovaj proizvod još nema spremljenih zapisa povijesti.")
