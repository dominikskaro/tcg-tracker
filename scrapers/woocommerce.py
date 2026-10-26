import time, requests
import re
import html
from games import infer_game

HEADERS = {"User-Agent": "Mozilla/5.0 (personal price tracker; contact: tvoj@email.com)"}

EXCLUDE = re.compile(
    r"\b(ruksak\w*|torba|torbe|ranac|ranci|sleeves?|playmat|binder|album|Sorcery TCG|Duskmourn|World of Tanks|Neuroscape TCG|"
    r"deck box|dice|kockic\w*|token|counter|loader\w*|toploader\w*|SWU|Star Wars|yu-gi-oh|Flesh\s+(?:&|and)\s+Blood|Sorcery\s*:\s*Contested Realm|"
    r"majica|pernica|šalica|ručnik|puzzle|slagalica|dragon shield|kofer|tcg lab|TcgLab)\b", re.I)

def fetch(shop):
    base = shop["base_url"]
    params = {"per_page": 100, "orderby": "date", "order": "desc"}
    if shop.get("category_id"):
        params["category"] = shop["category_id"]

    items, page = [], 1
    while True:
        params["page"] = page
        r = requests.get(f"{base}/wp-json/wc/store/v1/products",
                         params=params, headers=HEADERS, timeout=20)
        if r.status_code == 400:      # prošli smo zadnju stranicu
            break
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        for p in data:
            name = html.unescape(p["name"])
            if EXCLUDE.search(name):
                continue
            if shop.get("check_password_protected") and is_password_protected(
                p["permalink"]
            ):
                continue
            game = infer_game(name, p.get("categories", []))
            minor = p["prices"].get("currency_minor_unit", 2)
            items.append({
                "external_id": str(p["id"]),
                "name": html.unescape(p["name"]),
                "game": game,
                "url": p["permalink"],
                "price": int(p["prices"]["price"]) / (10 ** minor),
                "in_stock": bool(p["is_in_stock"]),
                "is_preorder": bool(p.get("is_on_backorder"))
                    or "pre-order" in p["name"].lower()
                    or "preorder" in p["name"].lower(),
                "barcode": p.get("sku"),
                "updated_at": None,    # Store API ne vraća datume
                "created_at": None,
            })
        page += 1
        time.sleep(1)
    return items          # redoslijed je već od najnovijeg prema starijem (server sortira)

def is_password_protected(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
    except requests.RequestException:
        return False

    page = html.unescape(response.text).casefold()
    markers = (
        "this content is password-protected",
        "enter the password below",
        'name="post_password"',
        "name='post_password'",
    )
    return any(marker in page for marker in markers)
