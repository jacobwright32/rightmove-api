# How to Extract New Features from extra_features Data

## Overview

The `extra_features` column in the `properties` table contains JSON arrays of free-text
strings scraped from Rightmove listings. The feature parser (`app/feature_parser.py`)
converts these into structured columns for ML modelling.

**Current state:** 74 features (41 v1 + 23 v2 + 10 v3), extracting ~466k values from ~205k properties.

## Step-by-step: Finding and Adding New Features

### 1. Scan for uncaptured patterns

Run this script to see what feature strings exist in the DB that aren't being captured:

```bash
cd /c/dev/rightmove-api
# Use ad-hoc SQL queries against the DB to scan for uncaptured patterns.
# Previous temp scripts (deep_feature_scan.py, fill_rates_v3.py) have been removed.
```

This approach gives you:
- **Uncaptured features with count >= 100** — raw strings not matched by any parser
- **Theme analysis** — grouped pattern frequencies (e.g. "storage: 5,526 (2.7%)")

Look for themes with >0.5% fill rate that are genuinely price-predictive.

### 2. Add a parser function

In `app/feature_parser.py`, add a new function following the existing pattern:

```python
def parse_has_FEATURE_NAME(features: list[str]) -> Optional[bool]:
    """Check for FEATURE_NAME."""
    for f in features:
        if re.search(r"YOUR_REGEX", f, re.I):
            return True
    return None
```

**Types of parsers:**
- **Boolean** — returns `True`/`None` (most common). E.g. `parse_has_cellar`
- **Categorical** — returns a string category or `None`. E.g. `parse_kitchen_type` → "Open Plan"/"Separate"/"Eat-in"
- **Numeric** — returns int/float or `None`. E.g. `parse_sq_ft` → 750

### 3. Register the feature in `parse_all_features()`

In `app/feature_parser.py`, add to the return dict in `parse_all_features()`:

```python
"feature_name": parse_has_FEATURE_NAME(features),
```

### 4. Add the key to `FEATURE_PARSER_KEYS`

In `app/constants.py`, append to the `FEATURE_PARSER_KEYS` list:

```python
"feature_name",
```

### 5. If categorical, register it in data_assembly.py

In `app/modelling/data_assembly.py`, add to `_CATEGORICAL_FEATURES` set:

```python
"feature_name",
```

(Skip this step for boolean and numeric features — they're auto-detected.)

### 6. Verify

```bash
# Run the parser tests (includes ~155 tests in test_feature_parser.py)
python -m pytest tests/ -q --tb=short --ignore=tests/test_api.py
```

### 7. Update the notebook

```bash
jupyter nbconvert --to notebook --execute notebooks/enriched_properties.ipynb \
  --output enriched_properties.ipynb --ExecutePreprocessor.timeout=600
```

## Files to modify

| File | What to change |
|------|---------------|
| `app/feature_parser.py` | Add parser function + add to `parse_all_features()` return dict |
| `app/constants.py` | Add key to `FEATURE_PARSER_KEYS` list |
| `app/modelling/data_assembly.py` | Add to `_CATEGORICAL_FEATURES` if categorical type |

## Remaining uncaptured themes (from deep scan)

These are patterns that exist in the data but don't yet have parsers. Sorted by count:

| Theme | Count | Fill% | Notes |
|-------|-------|-------|-------|
| bedrooms_count | 91,048 | 44.4% | Already in DB `bedrooms` column — skip |
| bathrooms_count | 33,798 | 16.5% | Already in DB `bathrooms` column — skip |
| bright_spacious | 25,498 | 12.4% | Subjective description — low modelling value |
| private_outdoor | 25,445 | 12.4% | Partially captured by `garden` parser |
| kitchen_desc | 17,346 | 8.4% | "Modern kitchen" etc — subjective |
| property_style | 17,161 | 8.4% | **CANDIDATE**: Detached/Semi/Terraced/Maisonette (but overlaps `property_type` DB field) |
| location_desc | 13,197 | 6.4% | "Excellent location" — subjective |
| bathroom_desc | 12,391 | 6.0% | "Modern bathroom" — subjective |
| communal_amenity | 10,820 | 5.3% | Partially captured by `garden` (communal garden) |
| security | 10,011 | 4.9% | **CANDIDATE**: CCTV/alarm/secure entry — partially captured by `gated` |
| close_to | 9,715 | 4.7% | Subjective proximity claims |
| condition_desc | 8,446 | 4.1% | Captured by `condition` and `refurbished` |
| storage | 5,526 | 2.7% | **CANDIDATE**: "ample storage" — boolean |
| recently_done | 5,568 | 2.7% | Captured by `refurbished` |
| transport_desc | 5,542 | 2.7% | Subjective transport claims |
| extension | 4,732 | 2.3% | ✅ Captured by `extended` (v3) |
| outbuilding | 3,856 | 1.9% | ✅ Captured (v3) |
| number_floors | 3,821 | 1.9% | ✅ Captured by enhanced `floor_level` |
| available_when | 3,821 | 1.9% | Listing metadata — low modelling value |
| potential_extend | 3,116 | 1.5% | ✅ Captured (v3) |
| no_fees | 2,808 | 1.4% | Rental listing metadata |
| zero_deposit | 2,652 | 1.3% | Rental listing metadata |
| sqm | 2,382 | 1.2% | ✅ Now converted to sq_ft automatically |
| residents_amenity | 2,271 | 1.1% | **CANDIDATE**: residents parking/gym/lounge |
| modern_generic | 2,036 | 1.0% | Subjective — skip |
| integrated_appliances | 1,974 | 1.0% | ✅ Captured (v3) |
| students | 1,802 | 0.9% | Rental listing metadata |
| eaves_storage | 547 | 0.3% | **CANDIDATE**: eaves/loft storage |
| walk_in_wardrobe | 516 | 0.3% | ✅ Captured (v3) |
| short_let | 499 | 0.2% | Rental metadata |
| pets | 449 | 0.2% | **CANDIDATE**: pets allowed/no pets |
| video_entry | 291 | 0.1% | ✅ Captured (v3) |
| bills_included | 803 | 0.4% | Rental metadata |
| wet_room | 160 | 0.1% | ✅ Captured (v3) |

**Best remaining candidates** (genuinely price-predictive, not yet captured):
1. `storage` — "ample storage" / "good storage" (2.7%)
2. `security` — CCTV / alarm system (4.9%, but overlaps `gated`)
3. `residents_parking` — residents parking (1.1%, overlaps `parking`)
4. `eaves_storage` — eaves/attic storage (0.3%)
5. `pets_allowed` — boolean (0.2%)

## Tips

- **Avoid false positives**: Test your regex against common feature strings.
  E.g. "garden" parser must not match "Covent Garden" (address).
- **Order matters in `parse_all_features()`**: For categorical parsers, the first
  match wins when multiple patterns could match the same string.
- **Use `re.I` flag**: Feature strings have inconsistent casing.
- **Keep fill rate >0.1%**: Features below this threshold add noise, not signal.
