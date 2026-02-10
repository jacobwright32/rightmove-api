# Rightmove House Prices API

A FastAPI application that scrapes and stores UK property data from Rightmove's house prices pages. Query by postcode, view sale histories, and optionally extract floorplan images.

## Features

- **Fast postcode scraping** — extracts property data from listing page embedded data (single HTTP request per page)
- **Multi-page pagination** — scrape multiple listing pages per postcode
- **Detail page scraping** — visit individual property pages for richer data (key features, full sale history, floorplans)
- **Floorplan extraction** — pull floorplan image URLs from property detail pages
- **Persistent storage** — SQLite database with upsert logic (no duplicates)
- **Query & filter** — search stored properties by postcode, type, bedrooms, etc.

## Prerequisites

- Python 3.9+
- pip

## Installation

```bash
git clone <repo-url>
cd rightmove-api
pip install -r requirements.txt
```

## Running

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## API Reference

### Scraping Endpoints

#### `POST /scrape/postcode/{postcode}`

Scrape properties for a UK postcode.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `postcode` | path | *required* | UK postcode (e.g. `E1W1AT`, `E1W-1AT`, `SW1A 2AA`) |
| `max_properties` | query | `50` | Maximum properties to return (1-500) |
| `pages` | query | `1` | Number of listing pages to scrape (1-50) |
| `link_count` | query | `null` | Visit this many detail pages for richer data (1-500) |
| `floorplan` | query | `false` | Extract floorplan image URLs (enables detail page visits) |

**Fast path** (default): Single HTTP request per listing page. Returns basic property info and latest transactions.

**Slow path** (when `link_count` or `floorplan=true`): Visits individual detail pages. Returns full sale history, key features, and optionally floorplan URLs.

```bash
# Fast: scrape first page
curl -X POST "http://localhost:8000/scrape/postcode/E1W1AT"

# Fast: scrape 3 pages, up to 100 properties
curl -X POST "http://localhost:8000/scrape/postcode/E1W1AT?pages=3&max_properties=100"

# Slow: visit 5 detail pages with floorplans
curl -X POST "http://localhost:8000/scrape/postcode/E1W1AT?link_count=5&floorplan=true"
```

**Response:**
```json
{
  "message": "Scraped 20 properties for postcode E1W1AT",
  "properties_scraped": 20,
  "pages_scraped": 1,
  "detail_pages_visited": 0
}
```

#### `POST /scrape/property`

Scrape a single property by its Rightmove URL.

**Request body:**
```json
{
  "url": "https://www.rightmove.co.uk/house-prices/detail/...",
  "floorplan": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | string | *required* | Rightmove property detail URL |
| `floorplan` | bool | `false` | Extract floorplan image URLs |

**Response:**
```json
{
  "message": "Scraped property: 123 Example Street, London E1W 1AT",
  "property": {
    "id": 1,
    "address": "123 Example Street, London E1W 1AT",
    "postcode": "E1W 1AT",
    "property_type": "TERRACED",
    "bedrooms": 3,
    "bathrooms": 1,
    "floorplan_urls": "[\"https://...\"]",
    "url": "https://www.rightmove.co.uk/house-prices/detail/...",
    "extra_features": "[\"Garden\", \"Parking\"]",
    "sales": [
      {
        "id": 1,
        "date_sold": "15 Jun 2023",
        "price": "£450,000",
        "price_change_pct": "",
        "property_type": "TERRACED",
        "tenure": "FREEHOLD"
      }
    ]
  }
}
```

### Query Endpoints

#### `GET /properties`

List stored properties with optional filters.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `postcode` | query | `null` | Filter by postcode (partial match) |
| `property_type` | query | `null` | Filter by property type (partial match) |
| `min_bedrooms` | query | `null` | Minimum number of bedrooms |
| `max_bedrooms` | query | `null` | Maximum number of bedrooms |
| `skip` | query | `0` | Pagination offset |
| `limit` | query | `50` | Page size (1-500) |

```bash
# All properties
curl "http://localhost:8000/properties"

# Filter by postcode and bedrooms
curl "http://localhost:8000/properties?postcode=E1W&min_bedrooms=2&max_bedrooms=3"
```

#### `GET /properties/{property_id}`

Get a single property with full sale history and details.

```bash
curl "http://localhost:8000/properties/1"
```

#### `GET /postcodes`

List all scraped postcodes with property counts.

```bash
curl "http://localhost:8000/postcodes"
```

**Response:**
```json
[
  {"postcode": "E1W 1AT", "property_count": 25},
  {"postcode": "SW1A 2AA", "property_count": 12}
]
```

## Data Model

### Property

| Field | Type | Description |
|---|---|---|
| `id` | int | Auto-increment primary key |
| `address` | string | Full address (unique) |
| `postcode` | string | Extracted UK postcode |
| `property_type` | string | e.g. TERRACED, FLAT, DETACHED |
| `bedrooms` | int | Number of bedrooms |
| `bathrooms` | int | Number of bathrooms |
| `extra_features` | JSON string | Key features list (from detail pages) |
| `floorplan_urls` | JSON string | Floorplan image URLs (from detail pages) |
| `url` | string | Rightmove detail page URL |
| `created_at` | datetime | First scraped |
| `updated_at` | datetime | Last updated |

### Sale

| Field | Type | Description |
|---|---|---|
| `id` | int | Auto-increment primary key |
| `property_id` | int | FK to Property |
| `date_sold` | string | e.g. "15 Jun 2023" |
| `price` | string | e.g. "£450,000" |
| `price_change_pct` | string | Percentage change from previous sale |
| `property_type` | string | Property type at time of sale |
| `tenure` | string | FREEHOLD or LEASEHOLD |

## Technical Details

- **Turbo Stream parsing**: Rightmove uses React Router v7 with Turbo Stream data format. Property data is embedded in `streamController.enqueue()` calls as a flat JSON array with reference keys.
- **Upsert logic**: Properties are matched by address. Re-scraping updates fields only when new data is non-empty, preserving existing data.
- **Date normalisation**: Leading zeros are stripped for consistent matching (e.g. "04 Nov" becomes "4 Nov").
- **Price normalisation**: All prices stored in "£N,NNN" format.
- **Case normalisation**: Property types and tenure are stored in uppercase.

## Limitations

- Data depends on what Rightmove makes publicly available on house-prices pages.
- Floorplan extraction relies on HTML/stream patterns that may change.
- Rate limiting: no built-in delays between requests. Add your own throttling for large scrapes.
- The database file (`rightmove.db`) is created relative to the working directory.
