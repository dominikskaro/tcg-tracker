import re, time, requests
from datetime import datetime
from games import infer_game

HEADERS = {"User-Agent": "Mozilla/5.0 (personal price tracker; contact: tvoj@email.com)"}

# Samo ono što želiš izbaciti iz TCG kategorije
EXCLUDE = re.compile(
    r"\b(sleeves?|playmat|binder|deck box|dice|single|token|counter|flesh and blood|star wars|yu-gi-oh|The Last Airbender|"
    r"dragon shield|kofer|tcg lab|TcgLab|PRO album|commander deck)\b", re.I)
CATALOG_EXCLUDE = re.compile(r"\b(grand archive|vampire)\b", re.I)

def is_preorder_product(product, tags):
    return (
        bool(tags & {"has-preorder-tag", "preorder", "pre-order"})
        or "prednarudžba" in str(product.get("vendor", "")).casefold()
        or re.search(
            r"\b(prednarudžba|pre-?order)\b",
            str(product.get("title", "")),
            re.I,
        ) is not None
    )

def fetch_paths(shop):
    paths = []
    if shop.get("collections"):
        paths.extend(f"/collections/{c}/products.json" for c in shop["collections"])
    else:
        paths.append("/products.json")

    if shop.get("include_tcg_catalog") and "/products.json" not in paths:
        paths.append("/products.json")

    return paths

def fetch(shop):
    base, seen, source_paths = shop["base_url"], {}, {}
    for path in fetch_paths(shop):
        page = 1
        while True:
            r = requests.get(base + path, params={"limit": 250, "page": page},
                             headers=HEADERS, timeout=20)
            r.raise_for_status()
            products = r.json()["products"]
            if not products:
                break
            for p in products:
                raw_tags = p.get("tags") or []
                if isinstance(raw_tags, str):
                    raw_tags = raw_tags.split(",")
                normalized_tags = {str(tag).strip().casefold() for tag in raw_tags}
                catalog_metadata = " ".join((
                    str(p.get("title", "")),
                    str(p.get("vendor", "")),
                    str(p.get("product_type", p.get("type", ""))),
                    *(str(tag) for tag in raw_tags),
                ))
                if (
                    shop.get("include_tcg_catalog")
                    and path == "/products.json"
                    and (
                        "tcg" not in normalized_tags
                        or not is_preorder_product(p, normalized_tags)
                        or CATALOG_EXCLUDE.search(catalog_metadata)
                    )
                ):
                    continue
                seen[p["id"]] = p
                if p["id"] not in source_paths or path.startswith("/collections/"):
                    source_paths[p["id"]] = path
            page += 1
            time.sleep(1)

    items = []
    for p in seen.values():
        title = p["title"]
        source_path = source_paths.get(p["id"], "")
        raw_tags = p.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.split(",")
        tags = {str(tag).strip().casefold() for tag in raw_tags}
        if EXCLUDE.search(title):
            continue
        v = p["variants"][0]
        product_type = p.get("product_type") or p.get("type") or ""
        product_type = re.sub(
            r"\s*(?:-\s*)?(?:prednarudžba|pre-?order)\s*$",
            "",
            str(product_type),
            flags=re.I,
        ).strip()
        vendor = str(p.get("vendor", ""))
        vendor_brand = re.sub(
            r"\s*-\s*(?:prednarudžba|pre-?order)\s*$", "", vendor, flags=re.I
        ).strip()
        if not product_type or product_type.casefold() in {"preorder", "pre-order"}:
            if vendor_brand and vendor_brand.casefold() != vendor.casefold():
                product_type = vendor_brand
        game = infer_game(title, product_type, vendor, raw_tags, source_path)
        match_name = title
        if product_type and product_type.casefold() not in title.casefold():
            match_name = f"{product_type}: {title}"
        items.append({
            "external_id": str(p["id"]),
            "name": title,
            "match_name": match_name,
            "game": game,
            "url": f'{base}/products/{p["handle"]}',
            "price": float(v["price"]),
            "in_stock": any(variant.get("available", "in-stock" in tags)
                for variant in p["variants"]),
            "is_preorder": is_preorder_product(p, tags),
            "barcode": v.get("barcode"),
            "updated_at": p["updated_at"],
            "created_at": p["created_at"],
        })
    items.sort(key=lambda i: datetime.fromisoformat(i["created_at"]), reverse=True)
    return items
