#!/usr/bin/env python3
"""Generate index.html from scraped property data."""
import json, os, re
from datetime import datetime

MAX_USD = 500_000

COUNTRY_MAP = {
    "costa_rica": {"region": "costa-rica", "name": "Costa Rica", "flag": "🇨🇷"},
    "panama":     {"region": "panama",     "name": "Panama",     "flag": "🇵🇦"},
    "belize":     {"region": "belize",     "name": "Belize",     "flag": "🇧🇿"},
}

def load_properties():
    path = os.path.join(os.path.dirname(__file__), "data", "properties.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["properties"]

def to_js_data(properties):
    """Convert scraped properties to JS DATA array entries."""
    entries = []
    for i, p in enumerate(properties):
        country_key = p.get("country", "panama")
        cm = COUNTRY_MAP.get(country_key, COUNTRY_MAP["panama"])
        
        price = p["price"]
        area = p.get("area_sqm") or 0
        beds_n = p.get("bedrooms") or 0
        beds_str = str(beds_n) if beds_n else "Studio"
        
        cad = int(price * 1.37)
        psqm = int(price / area) if area else 0
        
        airbnb_rate = p.get("airbnb_night_rate") or 0
        airbnb_occ = p.get("airbnb_occupancy_pct") or 0
        annual_income = int(airbnb_rate * (airbnb_occ / 100) * 365)
        gross_yield = round(annual_income / price * 100, 1) if price else 0
        gross_yield = min(gross_yield, 30.0)  # cap at 30% to avoid absurd values
        
        lat = p.get("lat", 0)
        lng = p.get("lng", 0)
        
        beach_lat = p.get("beach_lat", lat)
        beach_lng = p.get("beach_lng", lng)
        beach_url = p.get("beach_directions_url") or f"https://www.google.com/maps/dir/{lat},{lng}/{beach_lat},{beach_lng}"
        
        # Find nearest major city for the maps URL
        nearest_city = p.get("nearest_city", "")
        nearest_city_min = p.get("nearest_city_min") or 0
        
        maps_url = f"https://www.google.com/maps?q={lat},{lng}&z=14"
        
        entry = {
            "id": i,
            "title": p["title"],
            "price": price,
            "cad": cad,
            "area": area,
            "psqm": psqm,
            "beds": beds_str,
            "bedsN": beds_n,
            "roi": "",
            "ptype": p.get("property_type", "Property"),
            "region": cm["region"],
            "regionName": cm["name"],
            "airport": p.get("airport_drive_min") or 0,
            "airportName": f"{p.get('airport_name', '')} ({p.get('airport_code', '')})",
            "beach": p.get("beach_min") or 0,
            "beachKm": round(p.get("beach_km", 0), 1),
            "beachName": p.get("beach_name", ""),
            "beachUrl": beach_url,
            "reno": 1 if p.get("needs_renovation") else 0,
            "nearestCity": nearest_city,
            "nearestCityMin": nearest_city_min,
            "majorCity": nearest_city,
            "majorCityMin": nearest_city_min,
            "majorCityUrl": f"https://www.google.com/maps/dir/{lat},{lng}/{nearest_city}",
            "airbnbRate": airbnb_rate,
            "airbnbRateCad": int(airbnb_rate * 1.37),
            "airbnbOcc": airbnb_occ,
            "annualIncome": annual_income,
            "annualIncomeCad": int(annual_income * 1.37),
            "grossYield": gross_yield,
            "safety": p.get("safety_score") or 50,
            "safetyZone": p.get("safety_zone", ""),
            "lat": lat,
            "lng": lng,
            "mapsUrl": maps_url,
            "img": p.get("image_url", ""),
            "url": p.get("url", ""),
            "source": p.get("source", ""),
            "features": p.get("features", []),
            "areaPhotos": p.get("area_photos", []),
        }
        entries.append(entry)
    return entries

def generate():
    props = load_properties()
    js_data = to_js_data(props)
    
    # Read existing index.html
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    
    # Build new DATA array
    data_js = "const DATA = " + json.dumps(js_data, ensure_ascii=False, indent=None) + ";"
    
    # Replace DATA array
    pattern = r'const DATA = \[.*?\];'
    html = re.sub(pattern, data_js, html, count=1, flags=re.DOTALL)
    
    # Update counts
    count = len(props)
    countries = set()
    for p in props:
        ck = p.get("country", "")
        cm = COUNTRY_MAP.get(ck)
        if cm:
            countries.add(cm["flag"] + " " + cm["name"])
    countries_str = " · ".join(sorted(countries))
    
    max_cad = int(MAX_USD * 1.37 / 1000)
    html = re.sub(
        r'<div class="sub">.*?</div>',
        f'<div class="sub">{countries_str} — {count} real properties under CA${max_cad}k</div>',
        html, count=1
    )
    
    # Update footer
    today = datetime.now().strftime("%Y-%m-%d")
    sources = set(p.get("source","") for p in props)
    source_str = " &amp; ".join(sorted(sources))
    html = re.sub(
        r'<div class="footer">.*?</div>',
        f'<div class="footer">{count} properties · {source_str} · Data {today} · ⚠️ Verify before purchasing</div>',
        html, count=1
    )
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"✅ Updated index.html with {count} real properties")

if __name__ == "__main__":
    generate()
