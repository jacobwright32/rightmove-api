"""Parse structured fields from extra_features JSON arrays."""

import json
import re
from typing import Optional

# ── word-to-number mapping ──────────────────────────────────────────────────
_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_NUM_RE = re.compile(r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)", re.I)


def _to_int(s: str) -> Optional[int]:
    low = s.lower()
    if low in _WORD_NUM:
        return _WORD_NUM[low]
    try:
        return int(s)
    except ValueError:
        return None


# ── public parsers ──────────────────────────────────────────────────────────

def parse_epc_rating(features: list[str]) -> Optional[str]:
    """Extract EPC rating letter (A-G) from features list."""
    for f in features:
        m = re.search(r"(?:epc|energy).*?([A-G])\b", f, re.I)
        if m:
            return m.group(1).upper()
    return None


def parse_council_tax_band(features: list[str]) -> Optional[str]:
    """Extract council tax band letter (A-H)."""
    for f in features:
        m = re.search(r"council\s*tax.*?band\s*[-:.]?\s*([A-H])\b", f, re.I)
        if m:
            return m.group(1).upper()
    return None


def parse_chain_free(features: list[str]) -> Optional[bool]:
    """Determine if chain-free. Returns True/False/None."""
    for f in features:
        low = f.lower()
        if any(kw in low for kw in ("no onward chain", "chain free", "no chain")):
            return True
        if "end of chain" in low:
            return False
    return None


def parse_parking(features: list[str]) -> Optional[str]:
    """Categorise parking type."""
    for f in features:
        low = f.lower()
        if "garage" in low:
            return "Garage"
        if "driveway" in low:
            return "Driveway"
        if re.search(r"off[\s-]?street", low):
            return "Off-street"
        if "parking" in low:
            return "Parking"
    return None


def parse_garden(features: list[str]) -> Optional[str]:
    """Categorise garden/outdoor space type."""
    for f in features:
        low = f.lower()
        if "balcony" in low:
            return "Balcony"
        if (
            "terrace" in low
            and "terrace" not in low.split()[0:1]
            and ("roof" in low or "communal" in low or "private" in low or low.strip().endswith("terrace"))
        ):
            return "Terrace"
        if "communal" in low and "garden" in low:
            return "Communal Garden"
        if "private" in low and "garden" in low:
            return "Private Garden"
        if "patio" in low:
            return "Patio"
        if "garden" in low:
            return "Garden"
    return None


def parse_heating(features: list[str]) -> Optional[str]:
    """Categorise heating type."""
    for f in features:
        low = f.lower()
        if "underfloor" in low or "under floor" in low:
            return "Underfloor"
        if "gas" in low and ("central" in low or "heating" in low):
            return "Gas Central"
        if "central heating" in low:
            return "Central Heating"
        if "electric" in low and "heating" in low:
            return "Electric"
        if "heating" in low:
            return "Other"
    return None


def parse_double_glazed(features: list[str]) -> Optional[bool]:
    """Check if double glazed."""
    for f in features:
        if re.search(r"double\s*glaz", f, re.I):
            return True
    return None


def parse_lease(features: list[str]) -> tuple[Optional[str], Optional[int]]:
    """Extract lease type and years remaining."""
    lease_type = None
    lease_years = None

    for f in features:
        low = f.lower()
        if "share of freehold" in low:
            lease_type = "Share of Freehold"
        elif "freehold" in low and lease_type is None:
            lease_type = "Freehold"
        elif "leasehold" in low or "lease" in low:
            if lease_type is None:
                lease_type = "Leasehold"
            m = re.search(r"(\d+)\s*year", f, re.I)
            if m and lease_years is None:
                lease_years = int(m.group(1))

    if lease_years is None:
        for f in features:
            m = re.search(r"(\d+)\s*year\s*lease", f, re.I)
            if m:
                lease_years = int(m.group(1))
                if lease_type is None:
                    lease_type = "Leasehold"
                break

    return lease_type, lease_years


def parse_receptions(features: list[str]) -> Optional[int]:
    """Extract number of reception rooms."""
    for f in features:
        low = f.lower()
        m = re.match(r"(\d+|one|two|three|four|five)\s*reception", low)
        if m:
            return _to_int(m.group(1))
        if "reception room" in low:
            m = _NUM_RE.search(low)
            if m:
                return _to_int(m.group(1))
    return None


# ── NEW parsers ─────────────────────────────────────────────────────────────

def parse_furnished(features: list[str]) -> Optional[str]:
    """Extract furnished status: Furnished / Unfurnished / Part Furnished / None."""
    for f in features:
        low = f.lower().strip().rstrip(".")
        if "unfurnished" in low and "furnished" in low:
            return "Flexible"
        if "part furnished" in low or "part-furnished" in low:
            return "Part Furnished"
        if low in ("unfurnished", "unfurnished."):
            return "Unfurnished"
        if low == "furnished":
            return "Furnished"
    return None


def parse_period_property(features: list[str]) -> Optional[bool]:
    """Check if property has period features."""
    for f in features:
        if re.search(r"period\s*(features|property|house|home|character)", f, re.I):
            return True
    return None


def parse_has_utility_room(features: list[str]) -> Optional[bool]:
    """Check for utility room."""
    for f in features:
        if re.search(r"utility\s*room", f, re.I):
            return True
    return None


def parse_has_conservatory(features: list[str]) -> Optional[bool]:
    """Check for conservatory."""
    for f in features:
        if "conservatory" in f.lower():
            return True
    return None


def parse_has_ensuite(features: list[str]) -> Optional[bool]:
    """Check for en-suite bathroom."""
    for f in features:
        if re.search(r"en[\s-]?suite", f, re.I):
            return True
    return None


def parse_has_cloakroom(features: list[str]) -> Optional[bool]:
    """Check for downstairs cloakroom/WC."""
    for f in features:
        low = f.lower()
        if any(kw in low for kw in ("cloakroom", "downstairs wc", "downstairs w.c", "donwstairs wc", "separate wc")):
            return True
    return None


def parse_floor_level(features: list[str]) -> Optional[str]:
    """Extract floor level for flats/maisonettes."""
    for f in features:
        low = f.lower()
        if "ground floor" in low:
            return "Ground"
        if "first floor" in low:
            return "First"
        if "second floor" in low:
            return "Second"
        if "top floor" in low:
            return "Top"
        if "basement" in low or "lower ground" in low:
            return "Basement"
    return None


def parse_sq_ft(features: list[str]) -> Optional[int]:
    """Extract approximate square footage."""
    for f in features:
        # "Over 700sq ft", "797 Sq Ft", "3000 Sq Ft Plus", "1,200 sq ft"
        m = re.search(r"([\d,]+)\s*sq\s*\.?\s*ft", f, re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def parse_service_charge(features: list[str]) -> Optional[int]:
    """Extract annual service charge in pounds."""
    for f in features:
        # "Service Charge - £1,165 per annum", "Service Charge - £249.70 PA"
        m = re.search(r"service\s*(?:charge|/maintenance).*?[\u00a3$]([\d,]+(?:\.\d+)?)", f, re.I)
        if m:
            return int(float(m.group(1).replace(",", "")))
    return None


def parse_ground_rent(features: list[str]) -> Optional[int]:
    """Extract annual ground rent in pounds."""
    for f in features:
        m = re.search(r"ground\s*rent.*?[\u00a3$]([\d,]+(?:\.\d+)?)", f, re.I)
        if m:
            return int(float(m.group(1).replace(",", "")))
    return None


def parse_has_wooden_floors(features: list[str]) -> Optional[bool]:
    """Check for wooden/hardwood flooring."""
    for f in features:
        if re.search(r"wood(?:en)?\s*floor", f, re.I) or re.search(r"hardwood\s*floor", f, re.I):
            return True
    return None


def parse_has_gym(features: list[str]) -> Optional[bool]:
    """Check for gym (residents/communal)."""
    for f in features:
        if re.search(r"\bgym\b", f, re.I):
            return True
    return None


def parse_has_lift(features: list[str]) -> Optional[bool]:
    """Check for lift/elevator."""
    for f in features:
        low = f.lower().strip()
        if low == "lift" or "lift access" in low or "elevator" in low:
            return True
    return None


def parse_has_dining_room(features: list[str]) -> Optional[bool]:
    """Check for separate dining room."""
    for f in features:
        if re.search(r"\bdining\s*room\b", f, re.I):
            return True
    return None


def parse_has_ev_charger(features: list[str]) -> Optional[bool]:
    """Check for EV charger / charging point."""
    for f in features:
        if re.search(r"\bev\s*charg|charging\s*point", f, re.I):
            return True
    return None


def parse_has_fireplace(features: list[str]) -> Optional[bool]:
    """Check for fireplace/log burner."""
    for f in features:
        if re.search(r"fireplace|log\s*burner|wood\s*burner|open\s*fire|wood burning stove", f, re.I):
            return True
    return None


def parse_has_study(features: list[str]) -> Optional[bool]:
    """Check for study/home office."""
    for f in features:
        low = f.lower().strip()
        if low in ("study", "home office", "office", "study room"):
            return True
        if re.search(r"\bstudy\b", low) and len(low) < 30:
            return True
        if re.search(r"home\s*office|study/office|office/study", low):
            return True
    return None


def parse_has_shower_room(features: list[str]) -> Optional[bool]:
    """Check for separate shower room (distinct from bathroom)."""
    for f in features:
        if re.search(r"shower\s*room", f, re.I):
            return True
    return None


def parse_has_fitted_wardrobes(features: list[str]) -> Optional[bool]:
    """Check for fitted/built-in wardrobes."""
    for f in features:
        if re.search(r"fitted\s*wardrobe|built[\s-]?in\s*wardrobe", f, re.I):
            return True
    return None


def parse_new_build(features: list[str]) -> Optional[bool]:
    """Check if new build/development."""
    for f in features:
        if re.search(r"\bnew\s*build\b|new\s*development\b", f, re.I):
            return True
    return None


def parse_has_concierge(features: list[str]) -> Optional[bool]:
    """Check for concierge/porter service."""
    for f in features:
        if re.search(r"\bconcierge\b|\bporter\b", f, re.I):
            return True
    return None


def parse_has_swimming_pool(features: list[str]) -> Optional[bool]:
    """Check for swimming pool."""
    for f in features:
        if re.search(r"swimming\s*pool", f, re.I):
            return True
    return None


def parse_has_air_conditioning(features: list[str]) -> Optional[bool]:
    """Check for air conditioning."""
    for f in features:
        if re.search(r"air\s*condition", f, re.I):
            return True
    return None


def parse_has_solar_panels(features: list[str]) -> Optional[bool]:
    """Check for solar panels."""
    for f in features:
        if re.search(r"solar\s*panel", f, re.I):
            return True
    return None


def parse_has_loft(features: list[str]) -> Optional[bool]:
    """Check for loft room/conversion/storage."""
    for f in features:
        if re.search(r"\bloft\b", f, re.I):
            return True
    return None


def parse_has_entrance_hall(features: list[str]) -> Optional[bool]:
    """Check for entrance hall/hallway."""
    for f in features:
        if re.search(r"entrance\s*(hall|foyer)", f, re.I):
            return True
    return None


def parse_has_white_goods(features: list[str]) -> Optional[bool]:
    """Check for white goods included."""
    for f in features:
        low = f.lower()
        if "white goods" in low:
            return True
        if "dishwasher" in low or "washing machine" in low or "washer" in low:
            return True
    return None


def parse_has_bay_window(features: list[str]) -> Optional[bool]:
    """Check for bay window."""
    for f in features:
        if re.search(r"bay\s*window", f, re.I):
            return True
    return None


def parse_distance_to_station(features: list[str]) -> Optional[float]:
    """Extract distance to nearest station in miles."""
    for f in features:
        # "0.2 Miles to Raynes Park Station", "0.4 Miles From..."
        m = re.search(r"([\d.]+)\s*mile", f, re.I)
        if m and re.search(r"station", f, re.I):
            return float(m.group(1))
    return None


def parse_has_intercom(features: list[str]) -> Optional[bool]:
    """Check for intercom/entry phone system."""
    for f in features:
        if re.search(r"intercom|entry\s*phone|entryphone", f, re.I):
            return True
    return None


def parse_split_level(features: list[str]) -> Optional[bool]:
    """Check for split level property."""
    for f in features:
        if re.search(r"split\s*level", f, re.I):
            return True
    return None


# ── convenience: parse all fields at once ───────────────────────────────────

_ALL_KEYS = [
    "epc_rating", "council_tax_band", "chain_free", "parking", "garden",
    "heating", "double_glazed", "lease_type", "lease_years", "receptions",
    "furnished", "period_property", "utility_room", "conservatory", "ensuite",
    "cloakroom", "floor_level", "sq_ft", "service_charge", "ground_rent",
    "wooden_floors", "gym", "lift", "dining_room", "ev_charger", "fireplace",
    "study", "shower_room", "fitted_wardrobes", "new_build", "concierge",
    "swimming_pool", "air_conditioning", "solar_panels", "loft",
    "entrance_hall", "white_goods", "bay_window", "distance_to_station",
    "intercom", "split_level",
]


def parse_all_features(raw: Optional[str]) -> dict:
    """Parse a JSON extra_features string into a dict of structured fields."""
    features: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                features = [str(f).strip() for f in parsed if f]
        except (json.JSONDecodeError, TypeError):
            pass

    if not features:
        return {k: None for k in _ALL_KEYS}

    lease_type, lease_years = parse_lease(features)

    return {
        "epc_rating": parse_epc_rating(features),
        "council_tax_band": parse_council_tax_band(features),
        "chain_free": parse_chain_free(features),
        "parking": parse_parking(features),
        "garden": parse_garden(features),
        "heating": parse_heating(features),
        "double_glazed": parse_double_glazed(features),
        "lease_type": lease_type,
        "lease_years": lease_years,
        "receptions": parse_receptions(features),
        "furnished": parse_furnished(features),
        "period_property": parse_period_property(features),
        "utility_room": parse_has_utility_room(features),
        "conservatory": parse_has_conservatory(features),
        "ensuite": parse_has_ensuite(features),
        "cloakroom": parse_has_cloakroom(features),
        "floor_level": parse_floor_level(features),
        "sq_ft": parse_sq_ft(features),
        "service_charge": parse_service_charge(features),
        "ground_rent": parse_ground_rent(features),
        "wooden_floors": parse_has_wooden_floors(features),
        "gym": parse_has_gym(features),
        "lift": parse_has_lift(features),
        "dining_room": parse_has_dining_room(features),
        "ev_charger": parse_has_ev_charger(features),
        "fireplace": parse_has_fireplace(features),
        "study": parse_has_study(features),
        "shower_room": parse_has_shower_room(features),
        "fitted_wardrobes": parse_has_fitted_wardrobes(features),
        "new_build": parse_new_build(features),
        "concierge": parse_has_concierge(features),
        "swimming_pool": parse_has_swimming_pool(features),
        "air_conditioning": parse_has_air_conditioning(features),
        "solar_panels": parse_has_solar_panels(features),
        "loft": parse_has_loft(features),
        "entrance_hall": parse_has_entrance_hall(features),
        "white_goods": parse_has_white_goods(features),
        "bay_window": parse_has_bay_window(features),
        "distance_to_station": parse_distance_to_station(features),
        "intercom": parse_has_intercom(features),
        "split_level": parse_split_level(features),
    }
