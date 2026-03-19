#!/usr/bin/env python3
"""Detect and remove properties with AI-rendered/CGI photos."""
import json, os, sys, re, time

try:
    from curl_cffi import requests as cfreq
    def fetch(url, **kw):
        return cfreq.get(url, impersonate="chrome", **kw)
except ImportError:
    import requests as _req
    def fetch(url, **kw):
        return _req.get(url, **kw)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "properties.json")

# 3D rendering / AI software that might appear in EXIF
RENDER_SOFTWARE = [
    # 3D rendering engines
    b"V-Ray", b"VRay", b"Corona Render", b"Lumion", b"Enscape",
    b"Twinmotion", b"Blender", b"SketchUp", b"3ds Max", b"3dsmax",
    b"Cinema 4D", b"KeyShot", b"Octane", b"Unreal Engine", b"Unity",
    b"Autodesk", b"Revit", b"ArchiCAD",
    # AI generation
    b"DALL-E", b"dall-e", b"Midjourney", b"midjourney",
    b"Stable Diffusion", b"stable-diffusion", b"StableDiffusion",
    b"ComfyUI", b"AUTOMATIC1111", b"leonardo.ai", b"dream.ai",
    b"AI Generated", b"ai_generated",
    # C2PA / XMP AI markers  
    b"trainedAlgorithmicMedia", b"compositeWithTrainedAlgorithmicMedia",
    b"digitalArt", b"virtualRecording",
]

# Text keywords indicating unbuilt / render properties
RENDER_TEXT_KEYWORDS = [
    "pre-construction", "pre construction", "preconstruction",
    "off-plan", "off plan", "offplan", "preventa", "pre-venta",
    "under construction", "en construccion", "en construcción",
    "proyecto", "entrega 202", "delivery 202", "completion 202",
    "coming soon", "launching", "pre-sale", "presale",
]


def load_properties():
    with open(DATA_PATH) as f:
        return json.load(f)


def check_image_metadata(url, timeout=12):
    """Download image and check EXIF/XMP for render software markers."""
    try:
        r = fetch(url, timeout=timeout)
        if r.status_code != 200:
            return None, "download_failed"
        data = r.content
        if len(data) < 1000:
            return None, "too_small"
        
        # Search first 65KB for render software markers  
        search_region = data[:65536]
        for marker in RENDER_SOFTWARE:
            if marker in search_region:
                return True, f"metadata:{marker.decode(errors='replace')}"
        
        return False, "clean"
    except Exception as e:
        return None, f"error:{e}"


def is_text_flagged(prop):
    """Check title, features, and address for render/unbuilt indicators."""
    title = prop.get("title", "").lower()
    features = [f.lower() for f in prop.get("features", [])]
    addr = prop.get("display_address", "").lower()
    all_text = f"{title} {' '.join(features)} {addr}"
    
    # "New Construction" feature is a strong indicator of renders
    if "new construction" in all_text:
        return True, "new_construction_feature"
    
    for kw in RENDER_TEXT_KEYWORDS:
        if kw in all_text:
            return True, f"keyword:{kw}"
    
    return False, None


def detect_renders(props, check_images=True, max_image_checks=500):
    """
    Detect properties likely to have AI/CGI rendered photos.
    
    Strategy (conservative — only flag high-confidence renders):
    1. Text-based: "New Construction" feature, pre-construction keywords
    2. Metadata-based: EXIF/XMP markers from 3D render or AI software
    3. No image: properties with empty image URLs
    """
    flagged = []  # (prop, reason)
    clean = []
    
    # Pass 1: Text-based detection
    text_flagged_indices = set()
    for i, p in enumerate(props):
        is_flag, reason = is_text_flagged(p)
        if is_flag:
            flagged.append((p, reason))
            text_flagged_indices.add(i)
    
    print(f"  Text-based flags: {len(flagged)}")
    
    # Pass 2: No-image properties  
    no_img_count = 0
    for i, p in enumerate(props):
        if i in text_flagged_indices:
            continue
        if not p.get("image_url"):
            flagged.append((p, "no_image"))
            text_flagged_indices.add(i)
            no_img_count += 1
    print(f"  No-image flags: {no_img_count}")
    
    # Pass 3: Image metadata check
    if check_images:
        remaining = [(i, p) for i, p in enumerate(props) if i not in text_flagged_indices]
        print(f"  Checking {min(len(remaining), max_image_checks)} images for render metadata...")
        
        meta_flags = 0
        for idx, (i, p) in enumerate(remaining[:max_image_checks]):
            url = p.get("image_url", "")
            if not url:
                continue
            
            is_render, reason = check_image_metadata(url)
            if is_render:
                flagged.append((p, reason))
                text_flagged_indices.add(i)
                meta_flags += 1
            
            if (idx + 1) % 50 == 0:
                print(f"    Checked {idx+1}/{len(remaining)} images ({meta_flags} metadata flags)...")
            time.sleep(0.15)  # polite
        
        print(f"  Metadata flags: {meta_flags}")
    
    return flagged


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    data = load_properties()
    props = data["properties"]
    print(f"Total properties: {len(props)}")
    
    if mode == "analyze":
        # Quick text analysis only
        for p in props:
            is_flag, reason = is_text_flagged(p)
            if is_flag:
                print(f"  [TEXT] {reason}: {p['title'][:70]}")
        no_img = [p for p in props if not p.get("image_url")]
        print(f"No image: {len(no_img)}")
        for p in no_img:
            print(f"  [NO_IMG] {p['title'][:70]}")
    
    elif mode == "scan":
        # Full scan including image metadata (read-only)
        flagged = detect_renders(props, check_images=True)
        print(f"\n{'='*60}")
        print(f"FLAGGED: {len(flagged)} properties")
        print(f"{'='*60}")
        for p, reason in flagged:
            print(f"  [{reason}] {p['title'][:70]}")
        print(f"\nWould keep: {len(props) - len(flagged)} properties")
    
    elif mode == "filter":
        # Full scan + actually remove flagged properties
        flagged = detect_renders(props, check_images=True)
        flagged_urls = {p.get("url") for p, _ in flagged}
        
        filtered = [p for p in props if p.get("url") not in flagged_urls]
        
        print(f"\n{'='*60}")
        print(f"REMOVED {len(flagged)} properties:")
        for p, reason in flagged:
            print(f"  [{reason}] {p['title'][:70]}")
        print(f"KEPT: {len(filtered)} properties")
        print(f"{'='*60}")
        
        data["properties"] = filtered
        data["total_properties"] = len(filtered)
        with open(DATA_PATH, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved to {DATA_PATH}")
