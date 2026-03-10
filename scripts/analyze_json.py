import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

data = json.load(open("database/monitoring_line_map.json", encoding="utf-8"))

suffixes = {}
lines = set()
all_brands = set()
all_ids = set()

for line_key, items in data.items():
    parts = line_key.rsplit("_", 1)
    if len(parts) == 2 and parts[0].startswith("BT"):
        line_prefix = parts[0]
        suffix = parts[1]
    else:
        line_prefix = line_key
        suffix = line_key

    lines.add(line_prefix)

    for item in items:
        sp = item.split("|||")
        brand = sp[0].strip()
        mid = sp[1].strip() if len(sp) > 1 else "-"
        all_brands.add(brand)
        all_ids.add(mid)
        suffixes.setdefault(suffix, set()).add(brand)

print("=== Suffix -> Brands ===")
for s in sorted(suffixes):
    print(f"  {s:20s} -> {sorted(suffixes[s])}")

print(f"\n=== Lines ({len(lines)}) ===")
print(f"  {sorted(lines)}")

print(f"\n=== Unique Brands ({len(all_brands)}) ===")
print(f"  {sorted(all_brands)}")

print(f"\n=== Unique IDs ({len(all_ids)}) ===")
print(f"  {sorted(list(all_ids))[:10]}...")
