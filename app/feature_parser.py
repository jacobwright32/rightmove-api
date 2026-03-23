"""Parse structured fields from extra_features JSON arrays."""

import json
import re
from typing import Optional

from .constants import FEATURE_PARSER_KEYS, WORD_TO_NUMBER

_NUM_RE = re.compile(r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)", re.I)


def _to_int(s: str) -> Optional[int]:
    low = s.lower()
    if low in WORD_TO_NUMBER:
        return WORD_TO_NUMBER[low]
    try:
        return int(s)
    except ValueError:
        return None


# ── public parsers ──────────────────────────────────────────────────────────

def parse_epc_rating(features: list[str]) -> Optional[str]:
    """Extract EPC rating letter (A-G) from features list."""
    for f in features:
        m = re.search(r"(?:epc|energy)\b.*\b([A-G])\b", f, re.I)
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
        if any(kw in low for kw in (
            "no onward chain", "chain free", "no chain",
            "no forward chain", "chain-free",
        )):
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
        if "part furnished" in low or "part-furnished" in low:
            return "Part Furnished"
        if low == "unfurnished":
            return "Unfurnished"
        if low == "furnished":
            return "Furnished"
        if "unfurnished" in low and "furnished" in low.replace("unfurnished", ""):
            return "Flexible"
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
        if "ground floor" in low or "lower ground" in low:
            return "Ground"
        if "first floor" in low:
            return "First"
        if "second floor" in low:
            return "Second"
        if "third floor" in low or "3rd floor" in low:
            return "Third"
        if re.search(r"(fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|\d+th)\s*floor", low):
            return "Upper"
        if "top floor" in low:
            return "Top"
        if "basement" in low:
            return "Basement"
    return None


def parse_sq_ft(features: list[str]) -> Optional[int]:
    """Extract approximate square footage (also converts sq m to sq ft)."""
    for f in features:
        # "Over 700sq ft", "797 Sq Ft", "3000 Sq Ft Plus", "1,200 sq ft"
        m = re.search(r"([\d,]+)\s*sq\s*\.?\s*ft", f, re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    # Fallback: convert square metres to square feet
    for f in features:
        m = re.search(r"([\d,]+(?:\.\d+)?)\s*sq\s*\.?\s*m\b", f, re.I)
        if m:
            sqm = float(m.group(1).replace(",", ""))
            return int(round(sqm * 10.764))
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
            try:
                return float(m.group(1).rstrip("."))
            except ValueError:
                continue
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


# ── NEW v2 parsers ─────────────────────────────────────────────────────────


def parse_has_cellar(features: list[str]) -> Optional[bool]:
    """Check for cellar/basement storage space."""
    for f in features:
        low = f.lower()
        if "cellar" in low or "undercroft" in low:
            return True
        # Only match "basement" when it's clearly a room, not a floor level
        if low.strip() in ("basement", "basement room", "basement storage"):
            return True
    return None


def parse_has_roof_terrace(features: list[str]) -> Optional[bool]:
    """Check for roof terrace."""
    for f in features:
        if re.search(r"roof\s*terrace", f, re.I):
            return True
    return None


def parse_has_high_ceilings(features: list[str]) -> Optional[bool]:
    """Check for high ceilings."""
    for f in features:
        if re.search(r"high\s*ceiling", f, re.I):
            return True
    return None


def parse_has_open_plan(features: list[str]) -> Optional[bool]:
    """Check for open plan layout."""
    for f in features:
        if re.search(r"open[\s-]*plan", f, re.I):
            return True
    return None


def parse_has_gated(features: list[str]) -> Optional[bool]:
    """Check for gated development/community."""
    for f in features:
        if re.search(r"\bgated\b", f, re.I):
            return True
    return None


def parse_purpose_built(features: list[str]) -> Optional[bool]:
    """Check for purpose-built property."""
    for f in features:
        if re.search(r"purpose[\s-]*built", f, re.I):
            return True
    return None


def parse_refurbished(features: list[str]) -> Optional[bool]:
    """Check if recently refurbished/renovated."""
    for f in features:
        if re.search(
            r"(newly|recently)\s*(refurbish|renovate|decorat|fitted|updated)"
            r"|refurbished|renovated",
            f, re.I,
        ):
            return True
    return None


def parse_duplex(features: list[str]) -> Optional[bool]:
    """Check for duplex property."""
    for f in features:
        if re.search(r"\bduplex\b", f, re.I):
            return True
    return None


def parse_penthouse(features: list[str]) -> Optional[bool]:
    """Check for penthouse property."""
    for f in features:
        if re.search(r"\bpenthouse\b", f, re.I):
            return True
    return None


def parse_own_front_door(features: list[str]) -> Optional[bool]:
    """Check for own front door (independent entrance for a flat)."""
    for f in features:
        if re.search(r"own\s*front\s*door", f, re.I):
            return True
    return None


def parse_private_entrance(features: list[str]) -> Optional[bool]:
    """Check for private entrance."""
    for f in features:
        if re.search(r"private\s*entrance", f, re.I):
            return True
    return None


def parse_has_bike_storage(features: list[str]) -> Optional[bool]:
    """Check for bike/cycle storage."""
    for f in features:
        if re.search(r"(bike|cycle|bicycle)\s*stor", f, re.I):
            return True
    return None


def parse_cul_de_sac(features: list[str]) -> Optional[bool]:
    """Check for cul-de-sac location."""
    for f in features:
        if re.search(r"cul[\s-]*de[\s-]*sac", f, re.I):
            return True
    return None


def parse_conservation_area(features: list[str]) -> Optional[bool]:
    """Check if in a conservation area."""
    for f in features:
        if re.search(r"conservation\s*area", f, re.I):
            return True
    return None


def parse_has_annexe(features: list[str]) -> Optional[bool]:
    """Check for annexe/annex."""
    for f in features:
        if re.search(r"\bannex[e]?\b", f, re.I):
            return True
    return None


def parse_has_views(features: list[str]) -> Optional[bool]:
    """Check for notable views (river, sea, park, city, panoramic, etc.)."""
    for f in features:
        if re.search(
            r"(river|sea|park|garden|city|panoramic|rural|country|woodland|lake|"
            r"mountain|canal|harbour|harbor|ocean|thames)\s*view",
            f, re.I,
        ):
            return True
        if re.search(r"view(s)?\s*(of|over|across)\s*(the\s*)?(river|sea|park|city|thames|canal|lake)", f, re.I):
            return True
    return None


def parse_underground_parking(features: list[str]) -> Optional[bool]:
    """Check for underground/basement parking."""
    for f in features:
        if re.search(r"underground\s*park", f, re.I):
            return True
    return None


def parse_allocated_parking(features: list[str]) -> Optional[bool]:
    """Check for allocated parking space."""
    for f in features:
        if re.search(r"allocat\w*\s*park", f, re.I):
            return True
    return None


def parse_garden_facing(features: list[str]) -> Optional[str]:
    """Extract garden/property orientation: South, West, East, North."""
    for f in features:
        if re.search(r"south\s*fac", f, re.I):
            return "South"
        if re.search(r"west\s*fac", f, re.I):
            return "West"
        if re.search(r"east\s*fac", f, re.I):
            return "East"
        if re.search(r"north\s*fac", f, re.I):
            return "North"
    return None


def parse_property_era(features: list[str]) -> Optional[str]:
    """Extract property era: Victorian, Edwardian, Georgian, Art Deco, Period."""
    for f in features:
        low = f.lower()
        if "victorian" in low:
            return "Victorian"
        if "edwardian" in low:
            return "Edwardian"
        if "georgian" in low:
            return "Georgian"
        if re.search(r"art\s*deco", low):
            return "Art Deco"
    return None


def parse_condition(features: list[str]) -> Optional[str]:
    """Extract property condition: Excellent, Good, Immaculate, Fair."""
    for f in features:
        low = f.lower().strip()
        if re.search(r"\bimmaculate\b", low):
            return "Immaculate"
        if re.search(r"\bexcellent\s*condition\b", low):
            return "Excellent"
        if re.search(r"\bgood\s*condition\b", low):
            return "Good"
        if re.search(r"\bfair\s*condition\b", low):
            return "Fair"
    return None


def parse_kitchen_type(features: list[str]) -> Optional[str]:
    """Extract kitchen layout type."""
    for f in features:
        low = f.lower()
        if re.search(r"open[\s-]*plan\s*kitchen", low):
            return "Open Plan"
        if re.search(r"kitchen[\s/]*(din(er|ing)|breakfast)", low):
            return "Kitchen Diner"
        if re.search(r"eat[\s-]*in\s*kitchen", low):
            return "Eat-in"
        if re.search(r"separate\s*kitchen", low):
            return "Separate"
    return None


def parse_listed_building(features: list[str]) -> Optional[bool]:
    """Check for listed building status."""
    for f in features:
        if re.search(r"\blisted\s*(building|property|grade)", f, re.I):
            return True
        if re.search(r"grade\s*(i{1,3}|[12])\s*listed", f, re.I):
            return True
    return None


# ── NEW v3 parsers ─────────────────────────────────────────────────────────


def parse_extended(features: list[str]) -> Optional[bool]:
    """Check if property has been extended (side return, loft extension, etc.)."""
    for f in features:
        low = f.lower()
        if re.search(r"\bextend(ed|sion)\b", low) and "potential" not in low:
            return True
        if "side return" in low:
            return True
    return None


def parse_has_outbuilding(features: list[str]) -> Optional[bool]:
    """Check for outbuilding, garden room, summer house, workshop, etc."""
    for f in features:
        if re.search(
            r"\b(outbuilding|summer\s*house|garden\s*room|garden\s*office"
            r"|workshop|garden\s*studio|garden\s*shed)\b",
            f, re.I,
        ):
            return True
    return None


def parse_potential_to_extend(features: list[str]) -> Optional[bool]:
    """Check for potential to extend (STPP = Subject to Planning Permission)."""
    for f in features:
        if re.search(
            r"potential\s*(to\s*)?(extend|develop|convert|improve)"
            r"|stpp\b|subject\s*to\s*planning",
            f, re.I,
        ):
            return True
    return None


def parse_has_walk_in_wardrobe(features: list[str]) -> Optional[bool]:
    """Check for walk-in wardrobe/closet."""
    for f in features:
        if re.search(r"walk[\s-]*in\s*(wardrobe|closet|dressing)", f, re.I):
            return True
    return None


def parse_has_wet_room(features: list[str]) -> Optional[bool]:
    """Check for wet room."""
    for f in features:
        if re.search(r"wet\s*room", f, re.I):
            return True
    return None


def parse_has_integrated_appliances(features: list[str]) -> Optional[bool]:
    """Check for integrated/built-in kitchen appliances."""
    for f in features:
        if re.search(r"integrat\w*\s*appliance|built[\s-]*in\s*appliance", f, re.I):
            return True
    return None


def parse_has_side_access(features: list[str]) -> Optional[bool]:
    """Check for side access/passage."""
    for f in features:
        if re.search(r"side\s*(access|return|entrance|gate|passage)", f, re.I) and "extension" not in f.lower():
            return True
    return None


def parse_has_video_entry(features: list[str]) -> Optional[bool]:
    """Check for video entry/intercom/door system."""
    for f in features:
        if re.search(r"video\s*(entry|intercom|door)|door\s*entry", f, re.I):
            return True
    return None


def parse_has_separate_living_room(features: list[str]) -> Optional[bool]:
    """Check for separate sitting room/living room/drawing room/lounge."""
    for f in features:
        low = f.lower().strip()
        if low in ("sitting room", "living room", "drawing room", "lounge",
                    "living/dining room", "front room"):
            return True
        if re.search(r"^(separate|large|spacious|bright)\s*(sitting|living|drawing)\s*room$", low):
            return True
    return None


def parse_has_laminate_flooring(features: list[str]) -> Optional[bool]:
    """Check for laminate flooring."""
    for f in features:
        if re.search(r"laminate\s*floor", f, re.I):
            return True
    return None


# ── convenience: parse all fields at once ───────────────────────────────────



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
        return {k: None for k in FEATURE_PARSER_KEYS}

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
        # v2 features
        "cellar": parse_has_cellar(features),
        "roof_terrace": parse_has_roof_terrace(features),
        "high_ceilings": parse_has_high_ceilings(features),
        "open_plan": parse_has_open_plan(features),
        "gated": parse_has_gated(features),
        "purpose_built": parse_purpose_built(features),
        "refurbished": parse_refurbished(features),
        "duplex": parse_duplex(features),
        "penthouse": parse_penthouse(features),
        "own_front_door": parse_own_front_door(features),
        "private_entrance": parse_private_entrance(features),
        "bike_storage": parse_has_bike_storage(features),
        "cul_de_sac": parse_cul_de_sac(features),
        "conservation_area": parse_conservation_area(features),
        "annexe": parse_has_annexe(features),
        "views": parse_has_views(features),
        "underground_parking": parse_underground_parking(features),
        "allocated_parking": parse_allocated_parking(features),
        "garden_facing": parse_garden_facing(features),
        "property_era": parse_property_era(features),
        "condition": parse_condition(features),
        "kitchen_type": parse_kitchen_type(features),
        "listed_building": parse_listed_building(features),
        # v3 features
        "extended": parse_extended(features),
        "outbuilding": parse_has_outbuilding(features),
        "potential_to_extend": parse_potential_to_extend(features),
        "walk_in_wardrobe": parse_has_walk_in_wardrobe(features),
        "wet_room": parse_has_wet_room(features),
        "integrated_appliances": parse_has_integrated_appliances(features),
        "side_access": parse_has_side_access(features),
        "video_entry": parse_has_video_entry(features),
        "separate_living_room": parse_has_separate_living_room(features),
        "laminate_flooring": parse_has_laminate_flooring(features),
    }
