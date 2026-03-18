"""
Central America Property Finder — Web Scraper
Scrapes Rightmove Overseas for Costa Rica, Panama & Belize.
Computes beach & airport distances, fetches area photos from Wikimedia.
Budget: US$200,000 (~£155,000 GBP).
"""

import requests
from curl_cffi import requests as cffi_req
from bs4 import BeautifulSoup
import json
import re
import time
import os
import math
from datetime import datetime

# ── Currency conversion ────────────────────────────────────────────
GBP_TO_USD = 1.29   # March 2026 approx
MAX_USD = 500_000     # scrape up to $500k, frontend can filter further
MAX_GBP = int(MAX_USD / GBP_TO_USD)

# ── Central America airports ──────────────────────────────────────
AIRPORTS = {
    "SJO": {"name": "San José (SJO)", "lat": 9.9939, "lng": -84.2088, "country": "Costa Rica"},
    "LIR": {"name": "Liberia (LIR)", "lat": 10.5933, "lng": -85.5444, "country": "Costa Rica"},
    "PTY": {"name": "Panama City (PTY)", "lat": 9.0714, "lng": -79.3835, "country": "Panama"},
    "DAV": {"name": "David (DAV)", "lat": 8.3910, "lng": -82.4350, "country": "Panama"},
    "BZE": {"name": "Belize City (BZE)", "lat": 17.5391, "lng": -88.3082, "country": "Belize"},
}

# ── Major cities ──────────────────────────────────────────────────
CITIES = [
    {"name": "San José", "lat": 9.9281, "lng": -84.0907, "pop": 340000, "country": "Costa Rica"},
    {"name": "Liberia", "lat": 10.6346, "lng": -85.4407, "pop": 56000, "country": "Costa Rica"},
    {"name": "Jacó", "lat": 9.6155, "lng": -84.6277, "pop": 12000, "country": "Costa Rica"},
    {"name": "Tamarindo", "lat": 10.2994, "lng": -85.8375, "pop": 6000, "country": "Costa Rica"},
    {"name": "Panama City", "lat": 8.9824, "lng": -79.5199, "pop": 880000, "country": "Panama"},
    {"name": "David", "lat": 8.4272, "lng": -82.4310, "pop": 82500, "country": "Panama"},
    {"name": "Bocas Town", "lat": 9.3403, "lng": -82.2415, "pop": 13000, "country": "Panama"},
    {"name": "Boquete", "lat": 8.7792, "lng": -82.4413, "pop": 7000, "country": "Panama"},
    {"name": "Coronado", "lat": 8.5928, "lng": -79.9151, "pop": 25000, "country": "Panama"},
    {"name": "Belize City", "lat": 17.4987, "lng": -88.1857, "pop": 58000, "country": "Belize"},
    {"name": "San Pedro", "lat": 17.9181, "lng": -87.9589, "pop": 16000, "country": "Belize"},
    {"name": "San Ignacio", "lat": 17.1589, "lng": -89.0691, "pop": 20000, "country": "Belize"},
    {"name": "Belmopan", "lat": 17.2514, "lng": -88.7590, "pop": 23000, "country": "Belize"},
    {"name": "Placencia", "lat": 16.5141, "lng": -88.3661, "pop": 4000, "country": "Belize"},
]

# ── Distance helpers ──────────────────────────────────────────────

def _haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _osrm_route(lat1, lng1, lat2, lng2):
    try:
        url = (f"https://router.project-osrm.org/route/v1/driving/"
               f"{lng1},{lat1};{lng2},{lat2}?overview=false")
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            return round(route["distance"] / 1000, 1), max(1, int(route["duration"] / 60))
    except Exception:
        pass
    return None, None


def nearest_airport(lat, lng):
    best = None
    best_km = 9999
    for code, info in AIRPORTS.items():
        km = _haversine_km(lat, lng, info["lat"], info["lng"])
        if km < best_km:
            best_km = km
            best = (code, info)
    drive_min = int(best_km * 1.4 / 50 * 60) if best else 999
    code, info = best
    return code, info["name"], drive_min


def nearest_beach(lat, lng):
    """Use OSRM to find nearest coast point. Fallback to haversine estimate."""
    # For Central America, most beach areas are well-known.
    # We'll use a simplified approach: estimate from coordinates to nearest coast
    # Default: try OSRM to nearest known beach coordinate
    # Simplified: use Google Maps search link and estimate based on geography
    
    # Known beach coordinates for major beach areas
    BEACHES = [
        {"name": "Jacó Beach", "lat": 9.6155, "lng": -84.6310, "country": "Costa Rica"},
        {"name": "Tamarindo Beach", "lat": 10.2994, "lng": -85.8420, "country": "Costa Rica"},
        {"name": "Manuel Antonio Beach", "lat": 9.3920, "lng": -84.1432, "country": "Costa Rica"},
        {"name": "Playa Flamingo", "lat": 10.4380, "lng": -85.7889, "country": "Costa Rica"},
        {"name": "Nosara Beach", "lat": 9.9731, "lng": -85.6688, "country": "Costa Rica"},
        {"name": "Santa Teresa Beach", "lat": 9.6403, "lng": -85.1654, "country": "Costa Rica"},
        {"name": "Puerto Viejo Beach", "lat": 9.6589, "lng": -82.7540, "country": "Costa Rica"},
        {"name": "Playa Coco", "lat": 10.5533, "lng": -85.7081, "country": "Costa Rica"},
        {"name": "Ojochal Beach", "lat": 8.9256, "lng": -83.6828, "country": "Costa Rica"},
        {"name": "Bocas Beach", "lat": 9.3460, "lng": -82.2510, "country": "Panama"},
        {"name": "Playa Blanca", "lat": 8.3341, "lng": -80.1633, "country": "Panama"},
        {"name": "Coronado Beach", "lat": 8.5828, "lng": -79.9251, "country": "Panama"},
        {"name": "Playa Bonita", "lat": 9.3680, "lng": -79.8820, "country": "Panama"},
        {"name": "Pedasí Beach", "lat": 7.5277, "lng": -80.0269, "country": "Panama"},
        {"name": "San Pedro Beach", "lat": 17.9280, "lng": -87.9550, "country": "Belize"},
        {"name": "Caye Caulker Beach", "lat": 17.7467, "lng": -88.0220, "country": "Belize"},
        {"name": "Placencia Beach", "lat": 16.5141, "lng": -88.3680, "country": "Belize"},
        {"name": "Hopkins Beach", "lat": 16.8073, "lng": -88.2460, "country": "Belize"},
    ]
    
    candidates = []
    for b in BEACHES:
        km = _haversine_km(lat, lng, b["lat"], b["lng"])
        candidates.append((km, b))
    candidates.sort(key=lambda x: x[0])
    
    # Use haversine with road factor (faster than OSRM for bulk scraping)
    crow_km, best = candidates[0]
    best_road_km = round(crow_km * 1.3, 1)
    best_drive_min = max(1, int(best_road_km / 40 * 60))
    
    directions_url = f"https://www.google.com/maps/dir/{lat},{lng}/{best['lat']},{best['lng']}"
    return best["name"], best["lat"], best["lng"], best_road_km, best_drive_min, directions_url


def nearest_city(lat, lng):
    best = None
    best_km = 9999
    for c in CITIES:
        km = _haversine_km(lat, lng, c["lat"], c["lng"])
        if km < best_km:
            best_km = km
            best = c
    drive_min = int(best_km * 1.3 / 50 * 60) if best else 999
    return best["name"], best["pop"], max(5, drive_min)


def classify_country(lat, lng, display_address):
    addr = display_address.lower()
    if "costa rica" in addr:
        return "costa_rica"
    if "panama" in addr or "panamá" in addr:
        return "panama"
    if "belize" in addr:
        return "belize"
    # Coordinate-based fallback
    if lat and lng:
        if 7.0 < lat < 11.5 and -86.0 < lng < -82.5:
            return "costa_rica"
        if 7.0 < lat < 10.0 and -83.0 < lng < -77.0:
            return "panama"
        if 15.5 < lat < 18.5 and -89.5 < lng < -87.0:
            return "belize"
    return "unknown"


# ── Feature extraction ──────────────────────────────────────────────

def _extract_features(summary, ptype, bedrooms, addr):
    features = []
    s = (summary + " " + addr).lower()
    if bedrooms:
        features.append(f"{bedrooms} bedroom{'s' if bedrooms > 1 else ''}")
    if ptype:
        features.append(ptype)
    for kw, label in [
        ("renovated", "Renovated"), ("refurbished", "Refurbished"),
        ("sea view", "Sea View"), ("ocean view", "Ocean View"),
        ("mountain view", "Mountain View"), ("garden", "Garden"),
        ("terrace", "Terrace"), ("balcony", "Balcony"),
        ("pool", "Pool"), ("parking", "Parking"), ("furnished", "Furnished"),
        ("beachfront", "Beachfront"), ("near beach", "Near Beach"),
        ("gated", "Gated Community"), ("security", "Security"),
        ("central", "Central Location"), ("new", "New Construction"),
    ]:
        if kw in s and label not in features:
            features.append(label)
    return features[:6]


def _guess_renovation(summary, ptype):
    s = (summary or "").lower() + " " + (ptype or "").lower()
    if any(w in s for w in ("ruin", "renovation", "shell", "project", "fixer")):
        return True
    return False


def _estimate_airbnb(price_usd, country, bedrooms, beach_min, city_min):
    beds = bedrooms or 1
    if country == "costa_rica":
        base_rate = 55 + beds * 22
        base_occ = 52
    elif country == "panama":
        base_rate = 50 + beds * 20
        base_occ = 50
    elif country == "belize":
        base_rate = 60 + beds * 25
        base_occ = 48
    else:
        base_rate = 45 + beds * 18
        base_occ = 40
    if beach_min <= 10:
        base_rate += 15
        base_occ += 5
    elif beach_min <= 20:
        base_rate += 8
    if city_min <= 15:
        base_occ += 6
    return int(base_rate), min(72, int(base_occ))


# ── Wikimedia area photos ──────────────────────────────────────────

_PHOTO_BLACKLIST = re.compile(
    r'(logo|icon|map\b|flag|coat.of.arms|diagram|chart|stamp|sign\b|badge|seal|'
    r'placeholder|symbol|\.svg|ISS\d|View.of.Earth|'
    r'military|army|soldier|war|battle|troops|weapon|tank\b|'
    r'insect|beetle|bug|spider|ant|mosquito|'
    r'portrait|people.icon|fashion|coffee|'
    r'Coleoptera|arthropod)',
    re.IGNORECASE,
)

_WM_HEADERS = {"User-Agent": "CentralAmericaPropertyFinder/1.0"}


def _wikimedia_geosearch(lat, lng, radius_m=10000, limit=20):
    results = []
    try:
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "generator": "geosearch",
                "ggscoord": f"{lat}|{lng}", "ggsradius": str(radius_m),
                "ggsnamespace": "6", "ggslimit": str(limit),
                "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": "600",
                "format": "json",
            },
            headers=_WM_HEADERS, timeout=12,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for p in pages.values():
            fname = p.get("title", "")
            ii = (p.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            thumb = ii.get("thumburl", "")
            if not thumb or "image/" not in mime:
                continue
            if _PHOTO_BLACKLIST.search(fname):
                continue
            results.append(thumb)
    except Exception:
        pass
    return results


def _wikimedia_text_search(query, limit=10):
    results = []
    try:
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "generator": "search",
                "gsrsearch": query, "gsrnamespace": "6", "gsrlimit": str(limit),
                "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": "600",
                "format": "json",
            },
            headers=_WM_HEADERS, timeout=12,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for p in pages.values():
            fname = p.get("title", "")
            ii = (p.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            thumb = ii.get("thumburl", "")
            if not thumb or "image/" not in mime:
                continue
            if _PHOTO_BLACKLIST.search(fname):
                continue
            results.append(thumb)
    except Exception:
        pass
    return results


def _satellite_url(lat, lng):
    return (
        f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery"
        f"/MapServer/export?bbox={lng-0.015},{lat-0.01},{lng+0.015},{lat+0.01}"
        f"&bboxSR=4326&size=600,400&imageSR=4326&format=jpg&f=image"
    )


def fetch_area_photos(lat, lng, title, n=3):
    seen = set()
    results = []

    def _add(urls):
        for u in urls:
            if u not in seen:
                seen.add(u)
                results.append(u)

    if lat and lng:
        for radius in [5000, 10000, 20000]:
            _add(_wikimedia_geosearch(lat, lng, radius_m=radius))
            if len(results) >= n:
                break

    if len(results) < n:
        # Extract location hint from title
        hint = title
        if " - " in hint:
            hint = hint.split(" - ", 1)[1]
        hint = re.sub(r'\([^)]*\)', '', hint).strip()
        for part in hint.split(","):
            part = part.strip()
            if len(part) > 3 and part.lower() not in ("costa rica", "panama", "belize"):
                _add(_wikimedia_text_search(f'"{part}" landscape'))
                if len(results) >= n:
                    break

    if len(results) < n and lat and lng:
        _add([_satellite_url(lat, lng)])

    return results[:n]


# ── Rightmove Overseas Scraper ──────────────────────────────────────

def scrape_rightmove(country_name, max_pages=10):
    """Scrape Rightmove Overseas for a specific country."""
    properties = []
    seen_ids = set()

    for page_idx in range(max_pages):
        offset = page_idx * 24
        url = (
            f"https://www.rightmove.co.uk/overseas-property-for-sale/{country_name}.html"
            f"?sortType=1&index={offset}"
        )
        print(f"  [{country_name}] Page {page_idx + 1}: index={offset}...")
        try:
            r = cffi_req.get(url, impersonate="chrome", timeout=20)
            if r.status_code != 200:
                print(f"    HTTP {r.status_code}, skipping")
                continue

            soup = BeautifulSoup(r.text, "lxml")
            script = soup.find("script", id="__NEXT_DATA__")
            if not script or not script.string:
                print("    No __NEXT_DATA__ found")
                continue

            data = json.loads(script.string)
            page_props = data.get("props", {}).get("pageProps", {})

            raw_props = None
            for path_fn in [
                lambda: page_props["properties"],
                lambda: page_props["searchResults"]["properties"],
            ]:
                try:
                    raw_props = path_fn()
                    break
                except (KeyError, TypeError):
                    continue

            if not raw_props:
                def _find(d, key, depth=0):
                    if depth > 6 or not isinstance(d, dict):
                        return None
                    if key in d and isinstance(d[key], list) and d[key]:
                        return d[key]
                    for v in d.values():
                        r2 = _find(v, key, depth + 1)
                        if r2:
                            return r2
                    return None
                raw_props = _find(data, "properties") or []

            page_count = 0
            for rp in raw_props:
                pid = rp.get("id")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                # Price in USD
                price_data = rp.get("price", {})
                usd_price = None
                if isinstance(price_data, dict):
                    disp = price_data.get("displayPrices", [{}])
                    gbp_price = None
                    for dp in disp:
                        dstr = dp.get("displayPrice", "")
                        if "$" in dstr:
                            m = re.search(r'[\d,]+', dstr.replace(",", ""))
                            if m:
                                usd_price = int(m.group())
                        elif "£" in dstr:
                            m = re.search(r'[\d,]+', dstr.replace(",", ""))
                            if m:
                                gbp_price = int(m.group())
                    if not usd_price and gbp_price:
                        usd_price = int(gbp_price * GBP_TO_USD)
                    elif not usd_price:
                        amt = price_data.get("amount")
                        if amt:
                            usd_price = int(float(amt) * GBP_TO_USD)

                if not usd_price or usd_price > MAX_USD:
                    continue

                # Location
                loc = rp.get("location", {})
                lat = loc.get("latitude")
                lng = loc.get("longitude")
                display_addr = rp.get("displayAddress", "")

                if lat and lng:
                    lat = float(lat)
                    lng = float(lng)
                    # Sanity: Central America roughly lat 7-18, lng -90 to -77
                    if not (6 < abs(lat) < 19 and 76 < abs(lng) < 91):
                        lat, lng = None, None
                    if lng > 0:
                        lng = -lng  # Fix sign

                if not lat or not lng:
                    continue

                # Images
                images = rp.get("images", [])
                image_url = images[0].get("srcUrl", "") if images else ""

                # Property type
                ptype = rp.get("propertySubType", rp.get("propertyType", "Property"))
                bedrooms = rp.get("bedrooms")
                bathrooms = rp.get("bathrooms")

                # Title
                summary = rp.get("summary", "")
                beds_str = f"{bedrooms}-Bed " if bedrooms else ""
                title = f"{beds_str}{ptype} - {display_addr}" if display_addr else summary[:80]

                # Area
                area = None
                area_match = re.search(r'(\d+)\s*(?:sq\.?\s*m|m²|sqm|ft²)', summary, re.I)
                if area_match:
                    val = int(area_match.group(1))
                    if "ft" in area_match.group(0).lower():
                        val = int(val * 0.0929)  # sq ft to sqm
                    area = val

                # Skip plots/land
                if ptype and ptype.lower() in ("plot", "land", "plot of land"):
                    continue

                listing_url = f"https://www.rightmove.co.uk/properties/{pid}#/?channel=OVERSEAS"

                # Compute distances
                country = classify_country(lat, lng, display_addr)
                airport_code, airport_name, airport_min = nearest_airport(lat, lng)
                beach_name, beach_lat, beach_lng, beach_km, beach_min_val, beach_directions_url = nearest_beach(lat, lng)
                city_name, city_pop, city_min = nearest_city(lat, lng)
                airbnb_rate, airbnb_occ = _estimate_airbnb(usd_price, country, bedrooms, beach_min_val, city_min)

                prop = {
                    "title": title[:120],
                    "price": usd_price,
                    "area_sqm": area,
                    "bedrooms": bedrooms,
                    "bathrooms": bathrooms,
                    "url": listing_url,
                    "image_url": image_url,
                    "source": "Rightmove",
                    "country": country,
                    "display_address": display_addr,
                    "features": _extract_features(summary, ptype, bedrooms, display_addr),
                    "property_type": ptype or "Property",
                    "airport_drive_min": airport_min,
                    "airport_code": airport_code,
                    "airport_name": airport_name,
                    "beach_min": beach_min_val,
                    "beach_km": beach_km,
                    "beach_name": beach_name,
                    "beach_lat": beach_lat,
                    "beach_lng": beach_lng,
                    "beach_directions_url": beach_directions_url,
                    "nearest_city": city_name,
                    "nearest_city_pop": city_pop,
                    "nearest_city_min": city_min,
                    "needs_renovation": _guess_renovation(summary, ptype),
                    "airbnb_night_rate": airbnb_rate,
                    "airbnb_occupancy_pct": airbnb_occ,
                    "lat": lat,
                    "lng": lng,
                    "rightmove_id": pid,
                }
                properties.append(prop)
                page_count += 1

            print(f"    → {page_count} properties (total {len(properties)})")

            if page_count == 0:
                break  # No more results
            time.sleep(1.5)

        except Exception as e:
            print(f"    Error: {e}")

    return properties


# ── Realtor.com International Scraper ──────────────────────────────

REALTOR_PHOTO_BASE = "https://s1.rea.global/img/raw/"

def scrape_realtor(area_slug, max_pages=1):
    """Scrape Realtor.com International for an area via Apollo cache."""
    properties = []
    seen_ids = set()
    
    url = f"https://www.realtor.com/international/{area_slug}/"
    
    print(f"  [Realtor {area_slug}]...")
    for attempt in range(2):
        try:
            r = cffi_req.get(url, impersonate="chrome", timeout=45)
            if r.status_code != 200:
                print(f"    HTTP {r.status_code}")
                return properties
            break
        except Exception as e:
            if attempt == 0:
                print(f"    Timeout, retrying...")
                time.sleep(3)
                continue
            print(f"    Error: {e}")
            return properties
    
    try:
        
        soup = BeautifulSoup(r.text, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            print("    No __NEXT_DATA__ found")
            return properties
        
        data = json.loads(script.string)
        apollo = data.get("props", {}).get("apolloState", {})
        
        if not apollo:
            print("    No apolloState")
            return properties
        
        count = 0
        for k, v in apollo.items():
            if not k.startswith("ListingDetail:") or not isinstance(v, dict):
                continue
            
            lid = str(v.get("id", k.split(":")[-1]))
            if lid in seen_ids:
                continue
            seen_ids.add(lid)
            
            # Price
            price_key = f'$ListingDetail:{lid}.price({{"currency":"USD","language":"en"}})'
            price_data = apollo.get(price_key, {})
            price_str = price_data.get("displayListingPrice", "")
            price = None
            if price_str:
                m = re.search(r'[\d,]+', price_str.replace(",", ""))
                if m:
                    price = int(m.group())
            
            if not price or price > MAX_USD:
                continue

            # GeoLocation
            geo_key = f"$ListingDetail:{lid}.geoLocation"
            geo = apollo.get(geo_key, {})
            lat = geo.get("latitude") or geo.get("lat")
            lng = geo.get("longitude") or geo.get("lng")
            
            if not lat or not lng:
                continue
            
            lat = float(lat)
            lng = float(lng)
            
            # Photos
            photo_urls = []
            for i in range(20):
                photo_key = f"ListingDetail:{lid}.photos.{i}"
                photo_data = apollo.get(photo_key, {})
                path = photo_data.get("path", "")
                if path:
                    photo_urls.append(REALTOR_PHOTO_BASE + path)
            
            image_url = photo_urls[0] if photo_urls else ""
            
            # Detail URL
            detail_url_key = f'detailPageUrl({{"language":"en"}})'
            detail_path = v.get(detail_url_key, "")
            listing_url = f"https://www.realtor.com{detail_path}" if detail_path else ""
            
            # Property info
            bedrooms = v.get("bedrooms")
            bathrooms = v.get("bathrooms")
            display_addr = v.get("displayAddress", "")
            
            ptype_data = v.get('propertyTypes({"language":"en"})', {})
            ptype = ""
            if isinstance(ptype_data, dict) and "json" in ptype_data:
                ptypes = ptype_data["json"]
                ptype = ptypes[0] if ptypes else ""
            
            # Building size
            size_key = f'buildingSize({{"language":"en","unit":"SQUARE_FEET"}})'
            sqft_raw = v.get(size_key)
            area = None
            if sqft_raw:
                try:
                    area = int(float(str(sqft_raw).replace(",", "")) * 0.0929)
                except (ValueError, TypeError):
                    pass
            
            # Skip plots/land/industrial
            if ptype and any(w in ptype.lower() for w in ("plot", "land", "industrial", "warehouse", "commercial")):
                continue
            
            beds_str = f"{bedrooms}-Bed " if bedrooms else ""
            addr_clean = display_addr.split(",")[0].strip() if "," in display_addr else display_addr
            title = f"{beds_str}{ptype} - {addr_clean}" if addr_clean else f"{beds_str}{ptype}"
            
            country = classify_country(lat, lng, display_addr)
            airport_code, airport_name, airport_min = nearest_airport(lat, lng)
            beach_name, b_lat, b_lng, beach_km, beach_min_val, beach_dir_url = nearest_beach(lat, lng)
            city_name, city_pop, city_min = nearest_city(lat, lng)
            airbnb_rate, airbnb_occ = _estimate_airbnb(price, country, bedrooms, beach_min_val, city_min)
            
            prop = {
                "title": title[:120],
                "price": price,
                "area_sqm": area,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "url": listing_url,
                "image_url": image_url,
                "source": "Realtor.com",
                "country": country,
                "display_address": display_addr,
                "features": _extract_features("", ptype, bedrooms, display_addr),
                "property_type": ptype or "Property",
                "airport_drive_min": airport_min,
                "airport_code": airport_code,
                "airport_name": airport_name,
                "beach_min": beach_min_val,
                "beach_km": beach_km,
                "beach_name": beach_name,
                "beach_lat": b_lat,
                "beach_lng": b_lng,
                "beach_directions_url": beach_dir_url,
                "nearest_city": city_name,
                "nearest_city_pop": city_pop,
                "nearest_city_min": city_min,
                "needs_renovation": False,
                "airbnb_night_rate": airbnb_rate,
                "airbnb_occupancy_pct": airbnb_occ,
                "lat": lat,
                "lng": lng,
                "realtor_id": lid,
                "area_photos": photo_urls[1:4] if len(photo_urls) > 1 else [],
            }
            properties.append(prop)
            count += 1
        
        print(f"    → {count} properties (total {len(properties)})")
    
    except Exception as e:
        print(f"    Error: {e}")
    
    return properties


# ── Main scraper pipeline ──────────────────────────────────────────

def run_scraper():
    print("=" * 60)
    print("Central America Property Finder — Scraper")
    print(f"Budget: US${MAX_USD:,} (~£{MAX_GBP:,} GBP)")
    print("=" * 60)

    # Load existing data to accumulate across runs
    out_path = os.path.join(os.path.dirname(__file__), "data", "properties.json")
    existing_ids = set()
    all_properties = []
    if os.path.exists(out_path):
        try:
            with open(out_path, "r") as f:
                old = json.load(f)
            for p in old.get("properties", []):
                pid = p.get("rightmove_id") or p.get("realtor_id") or p.get("url")
                key = f"{p.get('source', '')}:{pid}"
                if key not in existing_ids:
                    existing_ids.add(key)
                    all_properties.append(p)
            print(f"Loaded {len(all_properties)} existing properties")
        except Exception:
            pass

    # Scrape each country from Rightmove
    for country in ["Costa-Rica", "Panama", "Belize"]:
        print(f"\n🔍 Scraping Rightmove: {country}...")
        props = scrape_rightmove(country, max_pages=5)
        new_props = []
        for p in props:
            pid = p.get("rightmove_id") or p.get("url")
            key = f"{p.get('source', '')}:{pid}"
            if key not in existing_ids:
                existing_ids.add(key)
                new_props.append(p)
        all_properties.extend(new_props)
        print(f"  ✓ {len(new_props)} new properties from {country}")

    # Scrape area-level pages from Realtor.com International
    realtor_area_slugs = [
        # Country-level (catch-all)
        "Costa-Rica", "Panama", "Belize",
        # Costa Rica regions
        "cr/guanacaste", "cr/puntarenas", "cr/limon",
        "cr/heredia", "cr/cartago", "cr/san-jose", "cr/alajuela",
        # Panama regions
        "pa/bocas-del-toro", "pa/panama-city", "pa/chiriqui",
        "pa/cocle", "pa/colon", "pa/panama-oeste", "pa/veraguas",
        # Belize regions
        "bz/ambergris-caye", "bz/cayo", "bz/belize-city", "bz/stann-creek",
        "bz/orange-walk", "bz/corozal", "bz/toledo",
    ]
    realtor_seen_ids = set()
    # Pre-populate with existing realtor IDs
    for p in all_properties:
        if p.get("realtor_id"):
            realtor_seen_ids.add(p["realtor_id"])
    for slug in realtor_area_slugs:
        print(f"\n🔍 Scraping Realtor.com: {slug}...")
        props = scrape_realtor(slug)
        # Deduplicate across areas by realtor_id
        new_props = []
        for p in props:
            rid = p.get("realtor_id")
            if rid and rid not in realtor_seen_ids:
                realtor_seen_ids.add(rid)
                new_props.append(p)
        all_properties.extend(new_props)
        print(f"  ✓ {len(new_props)} new properties from {slug}")
        time.sleep(3)

    # Deduplicate by composite key (source + id)
    seen = set()
    unique = []
    for p in all_properties:
        pid = p.get("rightmove_id") or p.get("realtor_id") or p.get("url")
        key = f"{p.get('source', '')}:{pid}"
        if key not in seen:
            seen.add(key)
            unique.append(p)
    all_properties = unique

    print(f"\n📊 Total unique properties: {len(all_properties)}")

    # Sort by price
    all_properties.sort(key=lambda x: x["price"])

    # Fetch area photos for Rightmove properties (Realtor already has photos)
    print("\n📸 Fetching area photos from Wikimedia...")
    for i, p in enumerate(all_properties):
        if p.get("source") == "Realtor.com" and p.get("area_photos"):
            continue
        print(f"  [{i+1}/{len(all_properties)}] {p['title'][:60]}...")
        p["area_photos"] = fetch_area_photos(p["lat"], p["lng"], p["title"])
        time.sleep(0.5)

    # Cap to cheapest 150 for site performance
    if len(all_properties) > 150:
        all_properties = all_properties[:150]
        print(f"  (capped to cheapest 150)")

    # Build output
    output = {
        "scraped_date": datetime.now().isoformat(),
        "total_properties": len(all_properties),
        "budget": f"US${MAX_USD:,}",
        "countries": ["Costa Rica", "Panama", "Belize"],
        "sources": ["Rightmove Overseas", "Realtor.com International"],
        "properties": all_properties,
    }

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "data", "properties.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(all_properties)} properties to {out_path}")
    return output


if __name__ == "__main__":
    run_scraper()
