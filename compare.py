import sqlite3
from collections import defaultdict
from matching import match_key

MIN_PRICE = 30
MIN_DIFF_PCT = 10

conn = sqlite3.connect("tcg.db")
listing_columns = {row[1] for row in conn.execute("PRAGMA table_info(listings)")}
match_name_column = "match_name" if "match_name" in listing_columns else "name"
groups = defaultdict(list)
for shop, name, match_name, price, url in conn.execute(
        f"SELECT shop, name, {match_name_column}, price, url "
        "FROM listings WHERE in_stock=1 AND price>=?",
        (MIN_PRICE,)):
    groups[match_key(match_name or name)].append((price, shop, name, url))

results = []
for lst in groups.values():
    if len({s for _, s, _, _ in lst}) < 2:
        continue
    lst.sort()
    cheapest, dearest = lst[0][0], lst[-1][0]
    pct = (dearest - cheapest) / dearest * 100
    if pct >= MIN_DIFF_PCT:
        results.append((pct, dearest - cheapest, lst))

results.sort(key=lambda r: r[0], reverse=True)

print(f"USPOREDBA CIJENA ({len(results)} proizvoda s razlikom od {MIN_DIFF_PCT} % naviše)\n")
for pct, diff, lst in results:
    print(lst[0][2])
    for price, shop, name, url in lst:
        mark = "  <- najjeftiniji" if price == lst[0][0] else ""
        print(f"   {shop:10} {price:7.2f} €{mark}")
    print(f"   razlika: {diff:.2f} € ({pct:.0f} %)\n")
