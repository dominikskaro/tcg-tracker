import requests

H = {"User-Agent": "Mozilla/5.0 (personal price tracker)"}
r = requests.get("https://svarogsden.com/wp-json/wc/store/v1/products/37230",
                 headers=H, timeout=20)
print("API STATUS:", r.status_code)
if not r.ok:
    print(r.text[:300])
    raise SystemExit

p = r.json()
print(p["id"], "|", p["name"])
print("type:", p["type"], "| has_options:", p["has_options"], "| variations:", len(p["variations"]))
print("is_in_stock:", p["is_in_stock"], "| is_on_backorder:", p["is_on_backorder"],
      "| is_purchasable:", p["is_purchasable"])
print("stock_availability:", p["stock_availability"])
print("add_to_cart:", p["add_to_cart"])
print("low_stock_remaining:", p.get("low_stock_remaining"))
print("categories:", [c["slug"] for c in p["categories"]])