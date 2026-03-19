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
MIN_USD = 54_745      # skip listings under ~CA$75k (75000/1.37)
MAX_USD = 364_964     # scrape up to ~CA$500k (500000/1.37)
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
    
    # Comprehensive beach/coastal points for Central America
    BEACHES = [
        # ── Costa Rica — Pacific Coast (north to south) ──
        {"name": "Playa del Coco", "lat": 10.553, "lng": -85.708, "country": "Costa Rica"},
        {"name": "Playa Hermosa (Guanacaste)", "lat": 10.572, "lng": -85.741, "country": "Costa Rica"},
        {"name": "Playa Flamingo", "lat": 10.438, "lng": -85.789, "country": "Costa Rica"},
        {"name": "Playa Conchal", "lat": 10.408, "lng": -85.798, "country": "Costa Rica"},
        {"name": "Tamarindo Beach", "lat": 10.299, "lng": -85.842, "country": "Costa Rica"},
        {"name": "Playa Langosta", "lat": 10.279, "lng": -85.845, "country": "Costa Rica"},
        {"name": "Playa Avellanas", "lat": 10.213, "lng": -85.860, "country": "Costa Rica"},
        {"name": "Playa Negra (Guanacaste)", "lat": 10.179, "lng": -85.863, "country": "Costa Rica"},
        {"name": "Nosara Beach", "lat": 9.973, "lng": -85.669, "country": "Costa Rica"},
        {"name": "Playa Sámara", "lat": 9.877, "lng": -85.531, "country": "Costa Rica"},
        {"name": "Playa Carrillo", "lat": 9.860, "lng": -85.498, "country": "Costa Rica"},
        {"name": "Santa Teresa Beach", "lat": 9.640, "lng": -85.165, "country": "Costa Rica"},
        {"name": "Montezuma Beach", "lat": 9.653, "lng": -85.069, "country": "Costa Rica"},
        {"name": "Playa Tambor", "lat": 9.722, "lng": -85.015, "country": "Costa Rica"},
        {"name": "Puntarenas Beach", "lat": 9.977, "lng": -84.838, "country": "Costa Rica"},
        {"name": "Jacó Beach", "lat": 9.616, "lng": -84.631, "country": "Costa Rica"},
        {"name": "Playa Hermosa (Jacó)", "lat": 9.575, "lng": -84.588, "country": "Costa Rica"},
        {"name": "Manuel Antonio Beach", "lat": 9.392, "lng": -84.143, "country": "Costa Rica"},
        {"name": "Playa Dominical", "lat": 9.252, "lng": -83.858, "country": "Costa Rica"},
        {"name": "Playa Uvita", "lat": 9.148, "lng": -83.769, "country": "Costa Rica"},
        {"name": "Ojochal Beach", "lat": 8.926, "lng": -83.683, "country": "Costa Rica"},
        {"name": "Playa Zancudo", "lat": 8.543, "lng": -83.186, "country": "Costa Rica"},
        {"name": "Playa Pavones", "lat": 8.393, "lng": -83.155, "country": "Costa Rica"},
        # ── Costa Rica — Caribbean Coast (north to south) ──
        {"name": "Tortuguero Beach", "lat": 10.558, "lng": -83.503, "country": "Costa Rica"},
        {"name": "Playa Limón", "lat": 9.979, "lng": -83.022, "country": "Costa Rica"},
        {"name": "Playa Bonita (Limón)", "lat": 9.996, "lng": -83.009, "country": "Costa Rica"},
        {"name": "Cahuita Beach", "lat": 9.736, "lng": -82.839, "country": "Costa Rica"},
        {"name": "Puerto Viejo Beach", "lat": 9.659, "lng": -82.754, "country": "Costa Rica"},
        {"name": "Playa Cocles", "lat": 9.637, "lng": -82.720, "country": "Costa Rica"},
        {"name": "Manzanillo Beach", "lat": 9.632, "lng": -82.653, "country": "Costa Rica"},
        # ── Panama — Pacific Coast (west to east) ──
        {"name": "Playa Barqueta", "lat": 8.205, "lng": -82.640, "country": "Panama"},
        {"name": "Playa Las Lajas", "lat": 7.992, "lng": -81.861, "country": "Panama"},
        {"name": "Playa Santa Catalina", "lat": 7.630, "lng": -81.237, "country": "Panama"},
        {"name": "Pedasí Beach", "lat": 7.528, "lng": -80.027, "country": "Panama"},
        {"name": "Playa Venao", "lat": 7.434, "lng": -80.163, "country": "Panama"},
        {"name": "Playa Blanca (Coclé)", "lat": 8.334, "lng": -80.163, "country": "Panama"},
        {"name": "Playa Coronado", "lat": 8.497, "lng": -79.944, "country": "Panama"},
        {"name": "Playa Corona", "lat": 8.503, "lng": -79.913, "country": "Panama"},
        {"name": "San Carlos Beach", "lat": 8.489, "lng": -79.960, "country": "Panama"},
        {"name": "Punta Chame Beach", "lat": 8.599, "lng": -79.711, "country": "Panama"},
        {"name": "Playa Veracruz", "lat": 8.888, "lng": -79.595, "country": "Panama"},
        {"name": "Amador Causeway Beach", "lat": 8.933, "lng": -79.553, "country": "Panama"},
        {"name": "Cinta Costera (Panama City)", "lat": 8.968, "lng": -79.540, "country": "Panama"},
        {"name": "Costa del Este Beach", "lat": 9.005, "lng": -79.476, "country": "Panama"},
        {"name": "Playa Bonita (Panama City)", "lat": 8.948, "lng": -79.575, "country": "Panama"},
        # ── Panama — Caribbean Coast ──
        {"name": "Isla Grande Beach", "lat": 9.600, "lng": -79.571, "country": "Panama"},
        {"name": "Portobelo Beach", "lat": 9.555, "lng": -79.654, "country": "Panama"},
        {"name": "Playa Langosta (Colón)", "lat": 9.392, "lng": -79.883, "country": "Panama"},
        {"name": "Bocas del Toro Beach", "lat": 9.346, "lng": -82.251, "country": "Panama"},
        {"name": "Red Frog Beach", "lat": 9.259, "lng": -82.194, "country": "Panama"},
        {"name": "Starfish Beach (Bocas)", "lat": 9.419, "lng": -82.321, "country": "Panama"},
        {"name": "San Blas Beach", "lat": 9.556, "lng": -78.931, "country": "Panama"},
        # ── Belize — Coast & Islands (north to south) ──
        {"name": "Corozal Town Beach", "lat": 18.391, "lng": -88.389, "country": "Belize"},
        {"name": "Ambergris Caye Beach", "lat": 17.928, "lng": -87.955, "country": "Belize"},
        {"name": "Caye Caulker Beach", "lat": 17.747, "lng": -88.022, "country": "Belize"},
        {"name": "Belize City Shore", "lat": 17.497, "lng": -88.183, "country": "Belize"},
        {"name": "Dangriga Beach", "lat": 16.966, "lng": -88.223, "country": "Belize"},
        {"name": "Hopkins Beach", "lat": 16.807, "lng": -88.246, "country": "Belize"},
        {"name": "Placencia Beach", "lat": 16.514, "lng": -88.368, "country": "Belize"},
        {"name": "Punta Gorda Beach", "lat": 16.098, "lng": -88.808, "country": "Belize"},
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


# ── Neighbourhood safety heuristic ─────────────────────────────────
# Based on well-known safe tourist/expat areas, embassy advisories, and
# general reputation.  Score 0–100 where 100 = safest.

SAFE_ZONES = [
    # Costa Rica — popular expat/tourist areas (high safety)
    {"name": "Tamarindo", "lat": 10.299, "lng": -85.838, "score": 82, "radius_km": 8},
    {"name": "Nosara", "lat": 9.973, "lng": -85.669, "score": 85, "radius_km": 8},
    {"name": "Manuel Antonio", "lat": 9.392, "lng": -84.143, "score": 80, "radius_km": 6},
    {"name": "Santa Teresa", "lat": 9.640, "lng": -85.165, "score": 78, "radius_km": 6},
    {"name": "Jacó", "lat": 9.616, "lng": -84.631, "score": 62, "radius_km": 5},
    {"name": "Playa Flamingo", "lat": 10.438, "lng": -85.789, "score": 80, "radius_km": 6},
    {"name": "Playa del Coco", "lat": 10.553, "lng": -85.708, "score": 72, "radius_km": 5},
    {"name": "Dominical", "lat": 9.252, "lng": -83.858, "score": 75, "radius_km": 6},
    {"name": "Uvita", "lat": 9.148, "lng": -83.769, "score": 78, "radius_km": 6},
    {"name": "Atenas", "lat": 9.975, "lng": -84.378, "score": 80, "radius_km": 6},
    {"name": "Grecia", "lat": 10.073, "lng": -84.312, "score": 78, "radius_km": 6},
    {"name": "San Ramón", "lat": 10.087, "lng": -84.469, "score": 76, "radius_km": 5},
    {"name": "Escazú", "lat": 9.920, "lng": -84.140, "score": 82, "radius_km": 5},
    {"name": "Santa Ana (CR)", "lat": 9.932, "lng": -84.182, "score": 82, "radius_km": 5},
    {"name": "Heredia", "lat": 10.002, "lng": -84.117, "score": 72, "radius_km": 5},
    {"name": "Sámara", "lat": 9.877, "lng": -85.531, "score": 78, "radius_km": 6},
    {"name": "Puerto Viejo", "lat": 9.659, "lng": -82.754, "score": 68, "radius_km": 5},
    {"name": "La Fortuna", "lat": 10.468, "lng": -84.643, "score": 76, "radius_km": 6},
    {"name": "San José Centro", "lat": 9.928, "lng": -84.091, "score": 48, "radius_km": 6},
    {"name": "Limón", "lat": 9.990, "lng": -83.044, "score": 38, "radius_km": 8},
    # Panama — safe areas
    {"name": "Boquete", "lat": 8.779, "lng": -82.441, "score": 88, "radius_km": 8},
    {"name": "Coronado (PA)", "lat": 8.593, "lng": -79.915, "score": 80, "radius_km": 8},
    {"name": "Panama City (safe zones)", "lat": 8.982, "lng": -79.520, "score": 68, "radius_km": 8},
    {"name": "Bocas del Toro", "lat": 9.340, "lng": -82.242, "score": 72, "radius_km": 8},
    {"name": "Pedasi", "lat": 7.528, "lng": -80.027, "score": 82, "radius_km": 8},
    {"name": "El Valle de Antón", "lat": 8.601, "lng": -80.127, "score": 85, "radius_km": 6},
    {"name": "Santa Catalina", "lat": 7.630, "lng": -81.237, "score": 75, "radius_km": 6},
    {"name": "David", "lat": 8.427, "lng": -82.431, "score": 65, "radius_km": 6},
    {"name": "Colón", "lat": 9.359, "lng": -79.901, "score": 32, "radius_km": 8},
    # Belize — safe areas
    {"name": "San Pedro (Ambergris)", "lat": 17.918, "lng": -87.959, "score": 78, "radius_km": 8},
    {"name": "Placencia", "lat": 16.514, "lng": -88.366, "score": 80, "radius_km": 6},
    {"name": "San Ignacio", "lat": 17.159, "lng": -89.069, "score": 72, "radius_km": 6},
    {"name": "Hopkins", "lat": 16.807, "lng": -88.246, "score": 76, "radius_km": 6},
    {"name": "Caye Caulker", "lat": 17.747, "lng": -88.022, "score": 75, "radius_km": 5},
    {"name": "Belize City", "lat": 17.499, "lng": -88.186, "score": 35, "radius_km": 8},
    {"name": "Corozal Town", "lat": 18.391, "lng": -88.389, "score": 65, "radius_km": 6},
    {"name": "Orange Walk", "lat": 18.090, "lng": -88.559, "score": 55, "radius_km": 6},
]

# Country-wide base safety (Numbeo safety index / 100 scaled)
COUNTRY_BASE_SAFETY = {
    "costa_rica": 50,
    "panama": 52,
    "belize": 42,
    "unknown": 40,
}


def neighbourhood_safety(lat, lng, country):
    """Estimate neighbourhood safety 0–100 based on proximity to known safe/unsafe zones."""
    base = COUNTRY_BASE_SAFETY.get(country, 40)

    best_score = base
    best_name = ""
    for zone in SAFE_ZONES:
        km = _haversine_km(lat, lng, zone["lat"], zone["lng"])
        if km <= zone["radius_km"]:
            # Inside the zone → use full score
            if zone["score"] > best_score:
                best_score = zone["score"]
                best_name = zone["name"]
        elif km <= zone["radius_km"] * 2.5:
            # Near the zone → blend toward zone score
            blend = 1 - (km - zone["radius_km"]) / (zone["radius_km"] * 1.5)
            blended = base + (zone["score"] - base) * blend
            if blended > best_score:
                best_score = int(blended)
                best_name = zone["name"]

    return min(100, max(0, int(best_score))), best_name


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

                # Skip plots/land/industrial
                if ptype and any(w in ptype.lower() for w in ("plot", "land", "industrial", "warehouse", "commercial", "farm", "garage", "townhouse")):
                    continue

                # Skip lots disguised as houses (check title/summary)
                _text_low = (title + " " + summary).lower()
                if any(w in _text_low.split() for w in LOT_TITLE_WORDS):
                    continue

                listing_url = f"https://www.rightmove.co.uk/properties/{pid}#/?channel=OVERSEAS"

                # Compute distances
                country = classify_country(lat, lng, display_addr)
                airport_code, airport_name, airport_min = nearest_airport(lat, lng)
                beach_name, beach_lat, beach_lng, beach_km, beach_min_val, beach_directions_url = nearest_beach(lat, lng)
                city_name, city_pop, city_min = nearest_city(lat, lng)
                airbnb_rate, airbnb_occ = _estimate_airbnb(usd_price, country, bedrooms, beach_min_val, city_min)
                safety_score, safety_zone = neighbourhood_safety(lat, lng, country)

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
                    "safety_score": safety_score,
                    "safety_zone": safety_zone,
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


# ── Realtor.com International Scraper (GraphQL) ───────────────────

REALTOR_PHOTO_BASE = "https://s1.rea.global/img/raw/"
REALTOR_GRAPHQL_URL = "https://www.rea.global/international/graphql"
REALTOR_GQL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.realtor.com",
    "Referer": "https://www.realtor.com/",
}
REALTOR_GQL_QUERY = """
{{
  searchListListings(
    listingSearchInput: {{
      boundingBoxSearch: null
      channel: "buy"
      country: "{country}"
      currencyCode: "USD"
      distanceUnit: "Miles"
      includesurrounding: true
      language: "en"
      searchtypes: []
      sort: ""
    }}
    pageReq: {{pageNo: {page}, pageSize: 200}}
  ) {{
    pageInfo {{ totalCount currentPageNo pageSize }}
    listings {{
      id
      displayAddress
      bedrooms
      bathrooms
      propertyTypes(language: "en")
      searchPropertyTypes
      detailPageUrl(language: "en")
      price(currency: "USD", language: "en") {{
        displayConsumerPrice
        hiddenPrice
      }}
      geoLocation {{ latitude longitude }}
      photos {{ type path }}
      location {{ country state city }}
    }}
  }}
}}
"""

LAND_WORDS = {"plot", "land", "industrial", "warehouse", "commercial", "farm",
              "garage", "office", "retail", "hotel", "leisure", "other", "townhouse"}
LOT_TITLE_WORDS = {"lot", "lote", "lots", "acres", "acre", "terrain", "terreno",
                   "finca", "parcela", "vacant", "solar", "hectare", "hectares"}


def scrape_realtor_graphql(country_code, max_pages=60):
    """Scrape Realtor.com via GraphQL API with pagination."""
    properties = []
    seen_ids = set()
    total_avail = "?"

    for page in range(1, max_pages + 1):
        q = REALTOR_GQL_QUERY.format(country=country_code, page=page)
        for attempt in range(2):
            try:
                r = cffi_req.post(
                    REALTOR_GRAPHQL_URL,
                    json={"query": q},
                    headers=REALTOR_GQL_HEADERS,
                    timeout=30,
                    impersonate="chrome",
                )
                break
            except Exception as e:
                if attempt == 0:
                    time.sleep(2)
                    continue
                print(f"    Page {page} error: {e}")
                return properties

        try:
            data = r.json()
        except Exception:
            print(f"    Page {page}: invalid JSON")
            break

        if "errors" in data:
            print(f"    Page {page} GraphQL error: {data['errors'][0]['message'][:100]}")
            break

        res = data.get("data", {}).get("searchListListings", {})
        listings = res.get("listings", [])
        if not listings:
            break

        pi = res.get("pageInfo", {})
        total_avail = pi.get("totalCount", "?")

        page_new = 0
        for l in listings:
            lid = str(l.get("id", ""))
            if not lid or lid in seen_ids:
                continue
            seen_ids.add(lid)

            # Price
            price_info = l.get("price") or {}
            if price_info.get("hiddenPrice"):
                continue
            price_str = price_info.get("displayConsumerPrice", "")
            price = None
            if price_str:
                m = re.search(r'[\d,]+', price_str.replace(",", ""))
                if m:
                    price = int(m.group())
            if not price or price > MAX_USD or price < MIN_USD:
                continue

            # Geo
            geo = l.get("geoLocation") or {}
            lat = geo.get("latitude")
            lng = geo.get("longitude")
            if not lat or not lng:
                continue
            lat, lng = float(lat), float(lng)

            # Property type filtering
            ptypes = l.get("propertyTypes") or []
            search_types = l.get("searchPropertyTypes") or []
            ptype = ptypes[0] if ptypes else ""
            all_types_str = " ".join(ptypes + search_types).lower()
            if any(w in all_types_str for w in LAND_WORDS):
                continue

            # Skip lots disguised as houses (check address/title text)
            _addr_low = display_addr.lower()
            if any(w in _addr_low.split() for w in LOT_TITLE_WORDS):
                continue

            # Photos
            photos = l.get("photos") or []
            photo_urls = []
            for ph in photos[:20]:
                path = ph.get("path", "")
                if path:
                    photo_urls.append(REALTOR_PHOTO_BASE + path)
            image_url = photo_urls[0] if photo_urls else ""

            # Detail URL
            detail_path = l.get("detailPageUrl", "")
            listing_url = f"https://www.realtor.com{detail_path}" if detail_path else ""

            # Info
            bedrooms = l.get("bedrooms")
            bathrooms = l.get("bathrooms")
            display_addr = l.get("displayAddress", "")

            beds_str = f"{bedrooms}-Bed " if bedrooms else ""
            addr_clean = display_addr.split(",")[0].strip() if "," in display_addr else display_addr
            title = f"{beds_str}{ptype} - {addr_clean}" if addr_clean else f"{beds_str}{ptype}"

            country = classify_country(lat, lng, display_addr)
            airport_code, airport_name, airport_min = nearest_airport(lat, lng)
            beach_name, b_lat, b_lng, beach_km, beach_min_val, beach_dir_url = nearest_beach(lat, lng)
            city_name, city_pop, city_min = nearest_city(lat, lng)
            airbnb_rate, airbnb_occ = _estimate_airbnb(price, country, bedrooms, beach_min_val, city_min)
            safety_score, safety_zone = neighbourhood_safety(lat, lng, country)

            prop = {
                "title": title[:120],
                "price": price,
                "area_sqm": None,
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
                "safety_score": safety_score,
                "safety_zone": safety_zone,
                "lat": lat,
                "lng": lng,
                "realtor_id": lid,
                "area_photos": photo_urls[1:4] if len(photo_urls) > 1 else [],
            }
            properties.append(prop)
            page_new += 1

        print(f"    Page {page}/{max_pages}: {len(listings)} listings, {page_new} in budget (total: {len(properties)}/{total_avail})")
        time.sleep(0.5)  # polite delay

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

    # Scrape each country from Realtor.com via GraphQL API
    realtor_countries = {"cr": "Costa Rica", "pa": "Panama", "bz": "Belize"}
    realtor_seen_ids = set()
    for p in all_properties:
        if p.get("realtor_id"):
            realtor_seen_ids.add(p["realtor_id"])

    for code, name in realtor_countries.items():
        print(f"\n🔍 Scraping Realtor.com GraphQL: {name} ({code})...")
        props = scrape_realtor_graphql(code)
        new_props = []
        for p in props:
            rid = p.get("realtor_id")
            if rid and rid not in realtor_seen_ids:
                realtor_seen_ids.add(rid)
                new_props.append(p)
        all_properties.extend(new_props)
        print(f"  ✓ {len(new_props)} new properties from {name}")

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

    # Filter out listings under minimum price
    before = len(all_properties)
    all_properties = [p for p in all_properties if p["price"] >= MIN_USD]
    if before != len(all_properties):
        print(f"  Removed {before - len(all_properties)} listings under US${MIN_USD:,}")

    # Filter out non-residential property types
    _skip_types = {"other", "offices", "retail", "hotel/leisure", "hotel", "warehouse", "industrial", "townhouse"}
    before = len(all_properties)
    all_properties = [p for p in all_properties if p.get("property_type", "").lower() not in _skip_types]
    if before != len(all_properties):
        print(f"  Removed {before - len(all_properties)} non-residential listings")

    # Deduplicate by image URL (catches same property listed under different names)
    seen_imgs = set()
    deduped = []
    for p in all_properties:
        img = p.get("image_url", "")
        if img and img in seen_imgs:
            continue
        if img:
            seen_imgs.add(img)
        deduped.append(p)
    if len(deduped) < len(all_properties):
        print(f"  Removed {len(all_properties) - len(deduped)} image-duplicate listings")
    all_properties = deduped

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

    # Select 150 properties spread evenly across the full price range
    MAX_SITE = 150
    if len(all_properties) > MAX_SITE:
        step = len(all_properties) / MAX_SITE
        all_properties = [all_properties[int(i * step)] for i in range(MAX_SITE)]
        print(f"  (sampled {MAX_SITE} across full price range: US${all_properties[0]['price']:,}–${all_properties[-1]['price']:,})")

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
