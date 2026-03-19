#!/usr/bin/env python3
"""Recalculate beach distances for all properties using updated BEACHES list."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from scraper import nearest_beach

path = os.path.join(os.path.dirname(__file__), "data", "properties.json")
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

updated = 0
for p in data["properties"]:
    lat = p.get("lat", 0)
    lng = p.get("lng", 0)
    if not lat or not lng:
        continue
    name, blat, blng, km, mins, url = nearest_beach(lat, lng)
    old_km = p.get("beach_km", 0)
    p["beach_name"] = name
    p["beach_lat"] = blat
    p["beach_lng"] = blng
    p["beach_km"] = km
    p["beach_min"] = mins
    p["beach_directions_url"] = url
    if abs(old_km - km) > 0.1:
        updated += 1
        print(f"  {p['title'][:40]:40s}  {old_km:6.1f}km → {km:6.1f}km  ({name})")

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n✅ Updated {updated} properties with new beach distances")
