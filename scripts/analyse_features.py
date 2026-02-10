"""Temporary script to categorize extra_features from parquet files."""
import glob
import json
import re
from collections import Counter

files = glob.glob("sales_data/**/*.parquet", recursive=True)

import pyarrow.parquet as pq

unique_features = Counter()

for f in files:
    t = pq.read_table(f, columns=["extra_features"])
    for val in t.column("extra_features").to_pylist():
        if val and val != "None":
            try:
                feats = json.loads(val)
                for feat in feats:
                    unique_features[feat.strip()] += 1
            except Exception:
                pass

categories = {
    "bedrooms": [],
    "bathrooms": [],
    "parking": [],
    "garden": [],
    "heating": [],
    "epc_rating": [],
    "council_tax": [],
    "chain_status": [],
    "property_type": [],
    "glazing": [],
    "lease": [],
    "kitchen": [],
    "reception": [],
    "other": [],
}

rules = [
    ("bedrooms", re.compile(r"(\d+|one|two|three|four|five|six)\s*(double\s*)?bed", re.I)),
    ("bathrooms", re.compile(r"(\d+|one|two|three|four|five)\s*bath", re.I)),
    ("parking", re.compile(r"parking|garage|driveway|off.street", re.I)),
    ("garden", re.compile(r"garden|balcony|terrace|patio|outdoor", re.I)),
    ("heating", re.compile(r"heating|underfloor|boiler", re.I)),
    ("epc_rating", re.compile(r"epc|energy", re.I)),
    ("council_tax", re.compile(r"council.tax", re.I)),
    ("chain_status", re.compile(r"chain|onward", re.I)),
    ("property_type", re.compile(r"detached|semi.detached|terraced|maisonette|flat|apartment|bungalow|cottage|penthouse|townhouse", re.I)),
    ("glazing", re.compile(r"glaz", re.I)),
    ("lease", re.compile(r"lease|freehold|share.of", re.I)),
    ("kitchen", re.compile(r"kitchen", re.I)),
    ("reception", re.compile(r"reception|lounge|living|sitting", re.I)),
]

for feat, count in unique_features.items():
    matched = False
    for cat_name, pattern in rules:
        if pattern.search(feat):
            categories[cat_name].append((feat, count))
            matched = True
            break
    if not matched:
        categories["other"].append((feat, count))

for cat, items in categories.items():
    items.sort(key=lambda x: -x[1])
    total = sum(c for _, c in items)
    print(f"\n=== {cat.upper()} ({len(items)} unique, {total} total) ===")
    for feat, cnt in items[:10]:
        print(f"  [{cnt:3d}] {feat}")
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")
