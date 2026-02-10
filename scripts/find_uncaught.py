"""Find features NOT caught by the current parser."""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, ".")

import pyarrow.parquet as pq

t = pq.read_table("sales_data/all_properties.parquet", columns=["extra_features"])
all_feats = []
for val in t.column("extra_features").to_pylist():
    if val is not None and val != "None":
        try:
            feats = json.loads(val)
            all_feats.extend([f.strip() for f in feats if f])
        except Exception:
            pass

# ALL patterns the current parser handles (original 10 + new 16)
CAUGHT_PATTERNS = [
    # Original 10 categories
    re.compile(r"(\d+|one|two|three|four|five|six)\s*(double\s*)?bed", re.I),
    re.compile(r"(\d+|one|two|three|four|five)\s*bath", re.I),
    re.compile(r"parking|garage|driveway|off.street", re.I),
    re.compile(r"garden|balcony|terrace|patio|outdoor", re.I),
    re.compile(r"heating|underfloor|boiler", re.I),
    re.compile(r"epc|energy", re.I),
    re.compile(r"council.tax", re.I),
    re.compile(r"chain|onward", re.I),
    re.compile(r"detached|semi.detached|terraced|maisonette|flat|apartment|bungalow", re.I),
    re.compile(r"glaz", re.I),
    re.compile(r"lease|freehold|share.of", re.I),
    re.compile(r"kitchen", re.I),
    re.compile(r"reception|lounge|living|sitting", re.I),
    # New 16 categories
    re.compile(r"^(un)?furnished", re.I),
    re.compile(r"part.furnished", re.I),
    re.compile(r"period\s*(features|property|house|home|character)", re.I),
    re.compile(r"utility\s*room", re.I),
    re.compile(r"conservatory", re.I),
    re.compile(r"en[\s-]?suite", re.I),
    re.compile(r"cloakroom|downstairs\s*w\.?c|separate\s*wc", re.I),
    re.compile(r"ground\s*floor|first\s*floor|second\s*floor|top\s*floor|basement|lower\s*ground", re.I),
    re.compile(r"\d[\d,]*\s*sq\s*\.?\s*ft", re.I),
    re.compile(r"service\s*(charge|/maintenance)", re.I),
    re.compile(r"ground\s*rent", re.I),
    re.compile(r"wood(?:en)?\s*floor|hardwood\s*floor", re.I),
    re.compile(r"\bgym\b", re.I),
    re.compile(r"\blift\b|elevator", re.I),
    re.compile(r"\bdining\s*room\b", re.I),
    re.compile(r"\bev\s*charg|charging\s*point", re.I),
    re.compile(r"fireplace|log\s*burner|wood\s*burner|open\s*fire", re.I),
]

uncaught = Counter()
for f in all_feats:
    if not any(p.search(f) for p in CAUGHT_PATTERNS):
        uncaught[f] += 1

print(f"Total feature mentions: {len(all_feats)}")
print(f"Caught: {len(all_feats) - sum(uncaught.values())}")
print(f"Uncaught: {sum(uncaught.values())} ({100*sum(uncaught.values())/len(all_feats):.1f}%)")
print(f"Uncaught unique: {len(uncaught)}")
print()
print("UNCAUGHT features (3+ occurrences):")
print()
for feat, count in uncaught.most_common():
    if count >= 3:
        try:
            print(f"  [{count:3d}] {feat}")
        except UnicodeEncodeError:
            print(f"  [{count:3d}] {feat.encode('ascii', 'replace').decode()}")
