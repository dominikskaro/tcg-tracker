import re, time, requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from games import infer_game

HEADERS = {"User-Agent": "Mozilla/5.0 (personal price tracker; contact: tvoj@email.com)"}

EXCLUDE_NAME = re.compile(
    r"mystery box|graded|sleeves?|playmat|binder|album|deck box|dice|acrylic case|portfolio|replica",
    re.I)
EXCLUDE_CATEGORY = re.compile(r"zašti|graded", re.I)
PREORDER_HINT = re.compile(
    r"\b(?:u\s+dolasku|prednarudžba|prednarudzba|pre[\s-]?order)\b", re.I
)
PREORDER_ORDERABLE = re.compile(r"\bu\s+dolasku\b", re.I)
RETRY_DELAYS = (2, 5, 10)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def parse_price(text):
    t = re.sub(r"[^\d,.]", "", text)          # "1.299,00 €" -> "1.299,00"
    t = t.replace(".", "").replace(",", ".")  # -> "1299.00"
    return float(t) if t else None


def get_page(url, page):
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = requests.get(
                url,
                params={"page": page},
                headers=HEADERS,
                timeout=20,
            )
        except (requests.ConnectionError, requests.Timeout) as error:
            if attempt == len(RETRY_DELAYS):
                raise
            delay = RETRY_DELAYS[attempt]
            print(
                f"SophosLab: privremeni prekid veze na stranici {page}; "
                f"ponovni pokušaj za {delay} s ({error})."
            )
            time.sleep(delay)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            if attempt == len(RETRY_DELAYS):
                response.raise_for_status()
            delay = RETRY_DELAYS[attempt]
            print(
                f"SophosLab: privremeni HTTP {response.status_code} "
                f"na stranici {page}; ponovni pokušaj za {delay} s."
            )
            time.sleep(delay)
            continue

        response.raise_for_status()
        return response


def fetch(shop):
    base = shop["base_url"]
    list_urls = list(dict.fromkeys((
        shop["list_url"],
        shop.get("preorder_list_url", shop["list_url"]),
    )))
    items_by_id = {}

    for list_url in list_urls:
        seen_on_list, page = set(), 1
        while page <= 30:                      # sigurnosna granica
            r = get_page(list_url, page)
            cards = BeautifulSoup(r.text, "html.parser").select("div.c-product-item")
            if not cards:
                if page == 1 and not items_by_id:
                    raise RuntimeError("nema proizvoda na prvoj stranici")
                break

            new = 0
            for card in cards:
                a = card.select_one(".c-product-name a")
                price_el = card.select_one(".c-product-price .current")
                if not a or not price_el:
                    continue
                href = a["href"]
                btn = card.select_one("button[data-id]")
                ext_id = btn["data-id"] if btn else href.rsplit("/", 1)[-1]
                if ext_id in seen_on_list:
                    continue
                seen_on_list.add(ext_id)
                new += 1

                name = a.get_text(strip=True)
                cat_el = card.select_one(".c-product-category")
                category = cat_el.get_text(strip=True) if cat_el else ""
                if EXCLUDE_NAME.search(name) or EXCLUDE_CATEGORY.search(category):
                    continue

                price = parse_price(price_el.get_text())
                if price is None:
                    continue
                avail = card.select_one(".c-product-availability")
                availability_text = avail.get_text(" ", strip=True) if avail else ""
                in_stock = bool(
                    re.search(r"\bdostup(?:an|na|no|ni)\b", availability_text, re.I)
                    and not re.search(r"\bne\s*dostup", availability_text, re.I)
                )
                preorder_hint = bool(
                    PREORDER_HINT.search(f"{name} {availability_text}")
                )
                product_url = urljoin(base, href)
                is_preorder = preorder_hint
                # SophosLab's preorder listing uses "U dolasku" for items
                # that can be added to cart; ordinary sold-out items stay excluded.
                orderable = in_stock or bool(
                    PREORDER_ORDERABLE.search(availability_text)
                )

                # Do not add ordinary sold-out products, but retain orderable preorders.
                if not orderable:
                    continue

                items_by_id[ext_id] = {
                    "external_id": ext_id,
                    "name": name,
                    "game": infer_game(name, category),
                    "url": product_url,
                    "price": price,
                    "in_stock": in_stock,
                    "is_preorder": is_preorder,
                    "orderable": orderable,
                    "barcode": None,
                    "updated_at": None,
                    "created_at": None,
                }

            if new == 0:                       # stranica nije donijela ništa novo
                break
            page += 1
            time.sleep(1)
    return list(items_by_id.values())
