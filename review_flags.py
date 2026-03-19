#!/usr/bin/env python3
import json

with open('data/properties.json') as f:
    props = json.load(f)['properties']

RENDER_TEXT_KEYWORDS = [
    'pre-construction', 'pre construction', 'preconstruction',
    'off-plan', 'off plan', 'under construction',
    'proyecto', 'nueva construccion',
    'render', 'rendering', 'artist impression',
    'concept', 'conceptual',
]

def is_text_flagged(p):
    blob = ' '.join([
        p.get('title',''),
        ' '.join(p.get('features',[])),
        p.get('display_address',''),
    ]).lower()
    return any(k in blob for k in RENDER_TEXT_KEYWORDS)

def has_new_construction(p):
    return 'New Construction' in p.get('features', [])

text_flagged = [p for p in props if is_text_flagged(p)]
new_const = [p for p in props if has_new_construction(p)]
no_image = [p for p in props if not p.get('image_url','').strip()]

print(f'Text keyword flagged: {len(text_flagged)}')
for p in text_flagged:
    print(f'  {p["title"][:80]}')

print(f'\nNew Construction feature: {len(new_const)}')
for p in new_const:
    print(f'  {p["title"][:80]}')
    print(f'      img: {p.get("image_url","")[:60]}')

print(f'\nNo image: {len(no_image)}')
for p in no_image:
    print(f'  {p["title"][:80]}')

# Compute overlap
all_flagged = set()
for p in text_flagged + new_const + no_image:
    all_flagged.add(p['url'])
print(f'\nUnique flagged: {len(all_flagged)}')
print(f'Remaining: {len(props) - len(all_flagged)}')
