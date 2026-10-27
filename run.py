import os
import time
import yaml
from datetime import datetime
from scrapers import shopify, woocommerce, sophoslab
from telegram_notify import send_events as send_telegram_events, send_status
import db

os.system("")   # uključuje podršku za hyperlink kodove u Windows terminalu

SCRAPERS = {"shopify": shopify, "woocommerce": woocommerce, "sophoslab": sophoslab}

def fmt_date(iso):
    if not iso:
        return "-"
    return datetime.fromisoformat(iso).astimezone().strftime("%d.%m.%Y %H:%M")

def link(url, text):
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"

with open("shops.yaml", encoding="utf-8") as f:
    shops = yaml.safe_load(f)["shops"]

NAME_W = 70

telegram_configured = bool(
    os.getenv("TCG_TELEGRAM_BOT_TOKEN") and os.getenv("TCG_TELEGRAM_CHAT_ID")
)
if not telegram_configured:
    print("Telegram obavijesti nisu uključene (nedostaje bot token ili chat ID).")

conn = db.connect()
all_shops_succeeded = True
failed_shops = []
inventory_warning_shops = []
for shop in shops:
    shop_started = time.perf_counter()
    try:
        items = SCRAPERS[shop["platform"]].fetch(shop)
    except Exception as e:
        all_shops_succeeded = False
        failed_shops.append(shop["name"])
        print(f"\nGREŠKA {shop['name']}: {e}")
        if telegram_configured:
            try:
                send_status(f"Greška pri dohvaćanju shopa {shop['name']}: {str(e)[:1000]}")
            except Exception as telegram_error:
                print(f"GREŠKA Telegram statusa: {telegram_error}")
        print(
            f"TRAJANJE SHOPA {shop['name']}: "
            f"{time.perf_counter() - shop_started:.1f} s (dohvat nije uspio)"
        )
        continue

    min_price = shop.get("min_price", 0)
    max_price = shop.get("max_price")
    in_stock = [i for i in items if i["in_stock"]]
    orderable = [i for i in items if i.get("orderable", i["in_stock"])]
    shown = [i for i in orderable
             if i["price"] >= min_price
             and (max_price is None or i["price"] <= max_price)]

    prev_stock = db.count_in_stock(conn, shop["name"])

    seed = db.is_empty(conn, shop["name"])
    events = db.apply_and_diff(conn, shop["name"], items, seed=seed)

    now_stock = sum(1 for i in items if i["in_stock"])
    if prev_stock >= 10 and now_stock < prev_stock * 0.5:
        inventory_warning_shops.append((shop["name"], prev_stock, now_stock))
        print(f"UPOZORENJE {shop['name']}: in stock pao s {prev_stock} na {now_stock}, "
              f"preskačem označavanje nestalih (moguć nepotpun dohvat)")
        if telegram_configured and not db.stock_drop_alert_is_active(conn, shop["name"]):
            try:
                send_status(
                    f"TCG Tracker: mogući nepotpun dohvat shopa {shop['name']}. "
                    f"Proizvoda na zalihi: {prev_stock} → {now_stock}. "
                    "Nisam označio nedostajuće proizvode kao rasprodane."
                )
                db.set_stock_drop_alert_active(conn, shop["name"], True)
            except Exception as telegram_error:
                print(f"GREŠKA Telegram upozorenja za {shop['name']}: {telegram_error}")
    else:
        db.set_stock_drop_alert_active(conn, shop["name"], False)
        gone = db.mark_missing(conn, shop["name"], items)
        if gone:
            print(f"(označeno kao nestalo: {gone})")

    fs = db.first_seen_map(conn, shop["name"])
    for i in items:
        if not i["created_at"]:
            i["created_at"] = fs.get(i["external_id"])
            i["created_approx"] = True

    events = [e for e in events
              if e["price"] >= min_price and (max_price is None or e["price"] <= max_price)]

    if telegram_configured and events:
        try:
            send_telegram_events(shop["name"], events)
        except Exception as e:
            print(f"GREŠKA Telegram obavijest ({shop['name']}): {e}")

    preorder_orderable = sum(
        1 for i in items if i.get("is_preorder") and i.get("orderable", False)
    )
    print(f"\n=== {shop['name']}: {len(shown)} prikazano "
          f"({len(in_stock)} in stock, {preorder_orderable} prednarudžbi za narudžbu, "
          f"{len(items)} ukupno u kategoriji) ===")
    print(f'{"KREIRANO":<17} | {"CIJENA":>8} | NAZIV (klikni za otvaranje)')
    print("-" * 17 + "-+-" + "-" * 8 + "-+-" + "-" * NAME_W)
    for i in shown:
        name = i["name"] + (" [PREORDER]" if i["is_preorder"] else "")
        if len(name) > NAME_W:
            name = name[:NAME_W - 1] + "…"
        padded = f"{name:<{NAME_W}}"
        print(f'{("~" if i.get("created_approx") else "") + fmt_date(i["created_at"]):<17} | {i["price"]:>6.2f} € | {link(i["url"], padded)}')

    # ---- OVO JE c), drugi dio (ispis događaja) ----
    if seed:
        print("\nPrvo pokretanje: stanje spremljeno, bez obavijesti.")
    for e in events:
        extra = f' (bilo {e["old_price"]:.2f} €)' if e["type"] == "PRICE_DROP" else ""
        print(f'{e["type"]:10} | {e["price"]:.2f} €{extra} | {e["name"]}')
    print(
        f"TRAJANJE SHOPA {shop['name']}: "
        f"{time.perf_counter() - shop_started:.1f} s"
    )

if all_shops_succeeded and not inventory_warning_shops:
    include_unavailable_preorders = {
        shop["name"] for shop in shops
        if shop["platform"] == "shopify"
        and shop.get("include_unavailable_preorders", False)
    }
    db.capture_product_baselines(conn, include_unavailable_preorders)

if telegram_configured:
    if all_shops_succeeded:
        final_status = "TCG Tracker: dohvat svih shopova završen bez tehničkih grešaka."
    else:
        final_status = (
            "TCG Tracker: djelomično ažurirano. Neuspješni shopovi: "
            + ", ".join(failed_shops)
            + "."
        )
    try:
        send_status(final_status)
    except Exception as e:
        print(f"GREŠKA Telegram završnog statusa: {e}")
