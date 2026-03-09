"""Centralised constants for the rightmove-api application.

Open this file when you need to update an API URL, tweak a timeout,
adjust a search radius, or modify a keyword list. All "updatable"
values live here; mathematical/geodetic constants, large reference
data, SQLite PRAGMAs, security headers, and app metadata stay in
their respective modules.
"""

import re

# ── External API URLs ────────────────────────────────────────────────────────
# Update these when an upstream provider changes their endpoint.

NAPTAN_CSV_URL = "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"

GIAS_BASE_URL = (
    "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/"
    "edubasealldata{date}.csv"
)

POSTCODES_IO_URL = "https://api.postcodes.io/postcodes"

EPC_BASE_URL = "https://epc.opendatacommunities.org/api/v1/domestic/search"

BROADBAND_URL = (
    "https://www.ofcom.org.uk/siteassets/resources/documents/"
    "research-and-data/multi-sector/infrastructure-research/"
    "connected-nations-2023/data-downloads/"
    "202305_fixed_postcode_performance_r01.zip"
)

POLICE_API_URL = "https://data.police.uk/api/crimes-street/all-crime"

EA_FLOOD_AREAS_URL = "https://environment.data.gov.uk/flood-monitoring/id/floodAreas"
EA_FLOOD_WARNINGS_URL = "https://environment.data.gov.uk/flood-monitoring/id/floods"

IMD_URL = (
    "https://assets.publishing.service.gov.uk/media/"
    "5dc407b440f0b6379a7acc8d/File_7_-_All_IoD2019_Scores__Ranks"
    "__Deciles_and_Population_Denominators_3.csv"
)

NSPL_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    "8a1d5b58df824b2e86fe07ddfdd87165/data"
)

GEOLYTIX_URL = (
    "https://drive.usercontent.google.com/download"
    "?id=1B8M7m86rQg2sx2TsHhFa2d-x-dZ1DbSy&export=download&confirm=t"
)

PLANNING_API_URL = "https://www.planning.data.gov.uk/entity.json"

GP_URL = (
    "https://www.odsdatasearchandexport.nhs.uk/api/getReport?report=epraccur"
)

HOSPITAL_URL = (
    "https://www.odsdatasearchandexport.nhs.uk/api/getReport?report=ets"
)

GREENSPACE_URL = (
    "https://api.os.uk/downloads/v1/products/OpenGreenspace/downloads"
    "?area=GB&format=GeoPackage&redirect"
)

RIGHTMOVE_BASE_URL = "https://www.rightmove.co.uk"

RIGHTMOVE_TYPEAHEAD_URL = "https://los.rightmove.co.uk/typeahead"


# ── HTTP Timeouts (seconds) ─────────────────────────────────────────────────
# Tune these if downloads are timing out or you want faster failure.

NAPTAN_TIMEOUT = 180
SCHOOLS_TIMEOUT = 120
GEOCODING_SINGLE_TIMEOUT = 10
GEOCODING_BATCH_TIMEOUT = 15
EPC_TIMEOUT = 15
BROADBAND_TIMEOUT = 300
CRIME_TIMEOUT = 15
FLOOD_TIMEOUT = 10
IMD_TIMEOUT = 120
ONS_TIMEOUT = 300
SUPERMARKETS_TIMEOUT = 300
PLANNING_TIMEOUT = 15
HEALTHCARE_TIMEOUT = 120
GREENSPACE_TIMEOUT = 600


# ── Search Radii & Thresholds ───────────────────────────────────────────────
# Distance limits (km) and search radii for spatial queries.

BUS_STOP_RADIUS_M = 500.0           # metres — bus stop count radius
SCHOOL_PRIMARY_RADIUS_KM = 2.0      # primary schools within
SCHOOL_SECONDARY_RADIUS_KM = 3.0    # secondary schools within
SUPERMARKET_RADIUS_KM = 2.0         # supermarkets within
GP_RADIUS_KM = 2.0                  # GP practices within
GREEN_SPACE_RADIUS_KM = 1.0         # green spaces within
FLOOD_WARNINGS_DIST_KM = "5"        # EA warnings search (string for API param)
FLOOD_AREAS_DIST_KM = "1"           # EA flood areas search (string for API param)


# ── Scraper Constants ────────────────────────────────────────────────────────
# Rightmove scraper settings — user agent, stream markers, pagination.

SCRAPER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

TURBO_STREAM_NULL = -5
TURBO_STREAM_UNDEFINED = -6

RIGHTMOVE_PAGE_SIZE = 24             # properties per for-sale search page
TYPEAHEAD_LIMIT = 5                  # max results from typeahead API

FLOORPLAN_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


# ── Crime API Behaviour ─────────────────────────────────────────────────────
# Cache duration, fetch window, rate-limiting, and retry logic.

CRIME_CACHE_DAYS = 30
CRIME_FETCH_MONTHS = 60
CRIME_API_DELAY = 0.2                # seconds between Police API calls
CRIME_MAX_RETRIES = 3
CRIME_RETRY_BACKOFF = 2.0            # seconds — doubled each retry
CRIME_FAILURE_THRESHOLD = 0.5        # fraction of months that can fail


# ── Planning Constants ───────────────────────────────────────────────────────
# Cache, limits, and heuristics for planning application lookups.

PLANNING_CACHE_DAYS = 30
PLANNING_DEFAULT_LIMIT = 50
PLANNING_MAX_LIMIT = 500
PLANNING_DWELLING_THRESHOLD = 10

PLANNING_MAJOR_KEYWORDS = [
    "demolition", "new build", "erection of", "residential development",
    "mixed use", "commercial", "industrial", "warehouse", "hotel",
    "student accommodation", "care home", "school", "hospital",
    "solar farm", "wind turbine", "infrastructure",
]


# ── Supermarket Brands ───────────────────────────────────────────────────────
# Add/remove brands to control which stores appear in proximity analysis.

PREMIUM_BRANDS = {"waitrose", "m&s food", "m&s simply food", "marks & spencer"}
BUDGET_BRANDS = {"aldi", "lidl"}

SUPERMARKET_BRANDS = {
    "tesco", "tesco express", "tesco extra", "tesco metro",
    "sainsburys", "sainsbury's", "sainsbury's local",
    "asda", "morrisons",
    "waitrose", "m&s food", "m&s simply food", "marks & spencer",
    "aldi", "lidl",
    "co-op", "cooperative", "the co-operative",
    "iceland", "farmfoods",
    "spar", "nisa", "costcutter", "budgens", "londis",
}


# ── Data Mappings ────────────────────────────────────────────────────────────
# Lookup tables used by enrichment modules.

EPC_RATING_COLORS = {
    "A": "#00C853",
    "B": "#66BB6A",
    "C": "#C6FF00",
    "D": "#FFEB3B",
    "E": "#FFB300",
    "F": "#FF6D00",
    "G": "#D50000",
}

FLOOD_RISK_LEVELS = {
    1: "very_low",
    2: "low",
    3: "medium",
}

IMD_DECILE_COLUMNS = {
    "Index of Multiple Deprivation (IMD) Decile": "imd_decile",
    "Income Decile": "imd_income_decile",
    "Employment Decile": "imd_employment_decile",
    "Education, Skills and Training Decile": "imd_education_decile",
    "Health Deprivation and Disability Decile": "imd_health_decile",
    "Crime Decile": "imd_crime_decile",
    "Barriers to Housing and Services Decile": "imd_housing_decile",
    "Living Environment Decile": "imd_environment_decile",
}

NAPTAN_STOP_TYPE_RAIL = "RSE"
NAPTAN_STOP_TYPE_METRO = "TMU"
NAPTAN_STOP_TYPE_BUS = "BCT"

GIAS_RETRY_DAYS = 8                  # how many dates back to try for GIAS CSV


# ── Regex Patterns ───────────────────────────────────────────────────────────
# Compiled patterns shared across modules.

OUTCODE_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)\s", re.IGNORECASE)

POSTCODE_PATTERN = r"(?:[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})"

CRIME_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

PLANNING_DWELLING_RE = re.compile(r"(\d+)\s*(dwelling|flat|apartment|house|unit)")

MONTH_ABBR_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── Feature Parser ───────────────────────────────────────────────────────────
# Word-to-number mapping and the canonical list of parsed feature keys.

WORD_TO_NUMBER = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

FEATURE_PARSER_KEYS = [
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
