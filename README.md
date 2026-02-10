# Rightmove House Prices API

A full-stack application for scraping, storing, and analyzing UK property sale data
from [Rightmove](https://www.rightmove.co.uk/house-prices.html). Combines a FastAPI
backend with a React frontend to provide on-demand data collection, queryable storage,
analytics, and interactive visualizations.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running the Server](#running-the-server)
  - [Running the Frontend](#running-the-frontend)
- [API Reference](#api-reference)
  - [Scraping](#scraping)
  - [Properties](#properties)
  - [Postcodes](#postcodes)
  - [Analytics](#analytics)
  - [Export](#export)
  - [Health](#health)
- [Data Model](#data-model)
- [Frontend](#frontend)
- [Testing](#testing)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)
- [Technical Details](#technical-details)
- [Limitations](#limitations)
- [License](#license)

---

## Features

| Category | Description |
|---|---|
| **Fast scraping** | Extracts property data from listing-page embedded data in a single HTTP request per page |
| **Detail scraping** | Visits individual property pages for full sale history, key features, and floorplan URLs |
| **Area scraping** | Scrapes all postcodes in an area from a partial postcode (e.g., "SW20" scrapes SW20 8NE, SW20 8NY, ...) |
| **Persistent storage** | SQLite database with upsert logic &mdash; re-scraping updates without duplicating |
| **Query & filter** | Search stored properties by postcode, type, bedrooms, with pagination |
| **Analytics** | Price trends, property type breakdowns, bedroom distributions, street comparisons, sales volume |
| **Dark mode** | Full dark theme with reactive Recharts chart theming |
| **Parquet export** | Export sales data to columnar Parquet files organized by outcode |
| **Rate limiting** | Configurable per-endpoint rate limits via slowapi |
| **Retry logic** | Exponential backoff with 429 handling for robust scraping |
| **CI/CD** | GitHub Actions pipeline with ruff linting, pytest, TypeScript checks, and frontend builds |

---

## Architecture

```
                                ┌─────────────────────┐
                                │   React Frontend    │
                                │  (Vite + Tailwind)  │
                                └────────┬────────────┘
                                         │ /api/v1/*
                                         ▼
┌────────────┐    HTTP     ┌─────────────────────────────┐
│  Rightmove │◄───────────►│       FastAPI Backend       │
│  (source)  │             │                             │
└────────────┘             │  ┌─────────┐ ┌───────────┐  │
                           │  │ Scraper │ │ Analytics │  │
                           │  │ Router  │ │  Router   │  │
                           │  └────┬────┘ └─────┬─────┘  │
                           │       │            │        │
                           │       ▼            ▼        │
                           │  ┌──────────────────────┐   │
                           │  │   SQLite Database    │   │
                           │  │   (rightmove.db)     │   │
                           │  └──────────────────────┘   │
                           └─────────────────────────────┘
```

**Backend:** FastAPI, SQLAlchemy, SQLite, BeautifulSoup4, slowapi

**Frontend:** React 19, TypeScript, Vite 6, Tailwind CSS 4, Recharts

---

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js 20+ (for frontend development)
- pip

### Installation

```bash
git clone https://github.com/jacobwright32/rightmove-api.git
cd rightmove-api

# Backend
pip install -r requirements.txt

# Frontend (optional — for development)
cd frontend
npm install
cd ..
```

### Configuration

Copy the example environment file and edit as needed:

```bash
cp .env.example .env
```

All settings have sensible defaults and work out of the box. See
[Configuration Reference](#configuration-reference) for the full list.

### Running the Server

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Interactive Swagger docs
at `http://localhost:8000/docs`.

### Running the Frontend

For development with hot reload:

```bash
cd frontend
npm run dev
```

Opens at `http://localhost:5173` with API requests proxied to the backend.

For production, build the frontend and let FastAPI serve it:

```bash
cd frontend
npm run build
cd ..
uvicorn app.main:app
```

The built frontend is served automatically from `frontend/dist/`.

---

## API Reference

All endpoints are prefixed with `/api/v1`. The interactive OpenAPI documentation is
available at `/docs` when the server is running.

### Scraping

#### `POST /api/v1/scrape/postcode/{postcode}`

Scrape properties for a UK postcode.

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `postcode` | string | UK postcode (e.g., `E1W1AT`, `E1W-1AT`, `SW1A 2AA`) |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_properties` | integer | `50` | Maximum properties to extract (1&ndash;500) |
| `pages` | integer | `1` | Listing pages to scrape (1&ndash;50) |
| `link_count` | integer | *null* | Detail pages to visit. `null` = fast mode, `0` = all |
| `floorplan` | boolean | `false` | Extract floorplan image URLs |
| `extra_features` | boolean | `false` | Extract key features list |
| `save_parquet` | boolean | `false` | Save each property to Parquet as it's scraped |

**Scraping modes:**

- **Fast mode** (default): One HTTP request per listing page. Returns basic property
  info and the most recent transaction.
- **Slow mode** (when `link_count`, `floorplan`, or `extra_features` is set): Visits
  individual property detail pages. Returns full sale history, key features, and
  floorplan URLs.

**Response:**

```json
{
  "message": "Scraped 20 properties for postcode E1W1AT",
  "properties_scraped": 20,
  "pages_scraped": 1,
  "detail_pages_visited": 0
}
```

**Status codes:** `200` Success | `404` No properties found | `429` Rate limited

**Examples:**

```bash
# Fast: scrape first page
curl -X POST "http://localhost:8000/api/v1/scrape/postcode/E1W1AT"

# Fast: scrape 3 pages, up to 100 properties
curl -X POST "http://localhost:8000/api/v1/scrape/postcode/E1W1AT?pages=3&max_properties=100"

# Slow: visit 5 detail pages with floorplans and features
curl -X POST "http://localhost:8000/api/v1/scrape/postcode/E1W1AT?link_count=5&floorplan=true&extra_features=true"
```

---

#### `POST /api/v1/scrape/area/{partial}`

Scrape all postcodes matching a partial postcode prefix.

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `partial` | string | Partial postcode (e.g., `SW20`, `E1W`) |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pages` | integer | `1` | Listing pages per postcode (1&ndash;50) |
| `link_count` | integer | *null* | Detail pages per postcode |
| `max_postcodes` | integer | `0` | Maximum postcodes to scrape (`0` = all) |
| `floorplan` | boolean | `false` | Extract floorplan image URLs |
| `extra_features` | boolean | `false` | Extract key features list |
| `save_parquet` | boolean | `false` | Save each property to Parquet |

**Response:**

```json
{
  "message": "Scraped 5 postcodes in area SW20",
  "postcodes_scraped": ["SW20 8NE", "SW20 8NY", "SW20 8ND", "SW20 0HG", "SW20 0HJ"],
  "postcodes_failed": [],
  "total_properties": 142
}
```

**Status codes:** `200` Success | `400` Invalid format | `404` No matching postcodes | `429` Rate limited

---

#### `POST /api/v1/scrape/property`

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
| `floorplan` | boolean | `false` | Extract floorplan image URLs |

**Response:**

```json
{
  "message": "Scraped property: 123 Example Street, London E1W 1AT",
  "property": { ... }
}
```

**Status codes:** `200` Success | `400` Not a Rightmove URL | `404` Could not extract data | `429` Rate limited

---

### Properties

#### `GET /api/v1/properties`

List stored properties with optional filters.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `postcode` | string | *null* | Filter by postcode (case-insensitive partial match) |
| `property_type` | string | *null* | Filter by property type (case-insensitive partial match) |
| `min_bedrooms` | integer | *null* | Minimum bedrooms |
| `max_bedrooms` | integer | *null* | Maximum bedrooms |
| `skip` | integer | `0` | Pagination offset |
| `limit` | integer | `0` | Maximum results (`0` = all) |

**Response:** Array of [PropertyDetail](#propertydetail) objects, ordered by `created_at` descending.

```bash
# All properties
curl "http://localhost:8000/api/v1/properties"

# Filter: 2-3 bed properties in E1W
curl "http://localhost:8000/api/v1/properties?postcode=E1W&min_bedrooms=2&max_bedrooms=3"
```

---

#### `GET /api/v1/properties/{property_id}`

Get a single property with its full sale history.

**Status codes:** `200` Success | `404` Not found

---

#### `GET /api/v1/properties/postcode/{postcode}/status`

Check whether data exists for a postcode.

**Response:**

```json
{
  "has_data": true,
  "property_count": 25,
  "last_updated": "2026-02-10T14:30:00"
}
```

---

### Postcodes

#### `GET /api/v1/postcodes`

List all postcodes that have been scraped, with property counts.

**Response:**

```json
[
  { "postcode": "E1W 1AT", "property_count": 25 },
  { "postcode": "SW1A 2AA", "property_count": 12 }
]
```

Ordered by `property_count` descending.

---

#### `GET /api/v1/postcodes/suggest/{partial}`

Autocomplete postcodes from a partial input. Checks both the database and
Rightmove for matches.

**Response:** `["SW20 8NE", "SW20 8NY", "SW20 8ND"]`

---

### Analytics

All analytics endpoints are under `/api/v1/analytics/postcode/{postcode}`.

| Endpoint | Description | Response type |
|---|---|---|
| `GET .../price-trends` | Monthly average, median, min, max prices | `PriceTrendPoint[]` |
| `GET .../property-types` | Count and average price per property type | `PropertyTypeBreakdown[]` |
| `GET .../bedroom-distribution` | Count and average price per bedroom count | `BedroomDistribution[]` |
| `GET .../street-comparison` | Average price per street | `StreetComparison[]` |
| `GET .../postcode-comparison` | Average price per full postcode | `PostcodeComparison[]` |
| `GET .../sales-volume` | Number of sales per year | `SalesVolumePoint[]` |
| `GET .../summary` | **All of the above in a single call** | `PostcodeAnalytics` |

**Status codes (all):** `200` Success | `404` No data for postcode

**Example &mdash; get full analytics summary:**

```bash
curl "http://localhost:8000/api/v1/analytics/postcode/SW20%208NE/summary"
```

<details>
<summary>Response schema (PostcodeAnalytics)</summary>

```json
{
  "postcode": "SW20 8NE",
  "price_trends": [
    {
      "month": "2023-06",
      "avg_price": 425000.0,
      "median_price": 410000.0,
      "min_price": 350000,
      "max_price": 550000,
      "count": 5
    }
  ],
  "property_types": [
    { "property_type": "TERRACED", "count": 12, "avg_price": 480000.0 }
  ],
  "street_comparison": [
    { "street": "High Street", "avg_price": 520000.0, "count": 8 }
  ],
  "postcode_comparison": [
    { "postcode": "SW20 8NE", "avg_price": 490000.0, "count": 15 }
  ],
  "bedroom_distribution": [
    { "bedrooms": 3, "count": 10, "avg_price": 450000.0 }
  ],
  "sales_volume": [
    { "year": 2023, "count": 12 }
  ]
}
```

</details>

---

### Export

#### `POST /api/v1/export/{postcode}`

Export all sales data for a postcode to Parquet files, organized by outcode.

**Response:**

```json
{
  "message": "Exported 25 properties",
  "properties_exported": 25,
  "files_written": 25,
  "output_dir": "sales_data/SW20"
}
```

**Status codes:** `200` Success | `404` No properties found

Files are written to `sales_data/{outcode}/{property_name}.parquet` using Snappy
compression.

---

### Health

#### `GET /health`

Health check endpoint with database connectivity verification.

**Response:**

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "ok"
}
```

Returns `"status": "degraded"` if the database is unreachable.

---

## Data Model

### Property

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | integer | PK, auto-increment | Unique identifier |
| `address` | string | unique, not null | Full property address |
| `postcode` | string | indexed | Extracted UK postcode |
| `property_type` | string | | e.g., TERRACED, FLAT, DETACHED |
| `bedrooms` | integer | | Number of bedrooms |
| `bathrooms` | integer | | Number of bathrooms |
| `extra_features` | text | | JSON array of key features |
| `floorplan_urls` | text | | JSON array of image URLs |
| `url` | string | | Rightmove detail page URL |
| `created_at` | datetime | default: now | First scraped timestamp |
| `updated_at` | datetime | auto-updates | Last updated timestamp |

### Sale

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | integer | PK, auto-increment | Unique identifier |
| `property_id` | integer | FK &rarr; Property, not null, indexed | Parent property |
| `date_sold` | string | | e.g., "15 Jun 2023" |
| `price` | string | | e.g., "£450,000" |
| `price_numeric` | integer | indexed | Parsed integer price in GBP |
| `date_sold_iso` | string | indexed | ISO 8601 date (YYYY-MM-DD) |
| `price_change_pct` | string | | Percentage change from prior sale |
| `property_type` | string | | Type at time of sale |
| `tenure` | string | | FREEHOLD or LEASEHOLD |

**Constraints:**

- Unique: `(property_id, date_sold, price)` &mdash; prevents duplicate sale records
- Compound index: `(property_id, date_sold_iso)` &mdash; optimizes time-series queries

### Response Schemas

#### PropertyDetail

```
id              int
address         string
postcode        string | null
property_type   string | null
bedrooms        int | null
bathrooms       int | null
extra_features  string | null     # JSON array
floorplan_urls  string | null     # JSON array
url             string | null
created_at      datetime | null
updated_at      datetime | null
sales           SaleOut[]
```

#### SaleOut

```
id                int
date_sold         string | null
price             string | null
price_numeric     int | null
date_sold_iso     string | null
price_change_pct  string | null
property_type     string | null
tenure            string | null
```

---

## Frontend

The React frontend provides:

- **Postcode search** with autocomplete suggestions
- **Scrape options** &mdash; pages, detail links, floorplans, key features, save-as-you-go
- **Analytics dashboard** &mdash; 6 interactive charts (price trends, property types,
  bedroom distribution, sales volume, street heatmap, postcode heatmap)
- **Property list** with expandable cards showing sale history, key features, and floorplans
- **Dark mode** with persistent preference (localStorage) and system detection
- **Export** to Parquet from the UI

### Component Structure

```
SearchPage
├── SearchBar (with postcode autocomplete)
├── LoadingOverlay
├── AnalyticsDashboard
│   ├── StatCard (x4)
│   ├── PriceTrendChart (LineChart)
│   ├── PropertyTypeChart (PieChart + BarChart)
│   ├── BedroomDistribution (BarChart)
│   ├── SalesVolumeTimeline (AreaChart)
│   ├── PriceHeatmap (street comparison grid)
│   ├── PostcodeHeatmap (postcode comparison grid)
│   └── PropertyList
│       └── PropertyCard (expandable)
│           └── SaleHistoryTable
└── ThemeToggle
```

---

## Testing

### Backend

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_api.py -v          # API integration tests
pytest tests/test_parsing.py -v      # Price/date parsing tests
pytest tests/test_scraper_utils.py -v  # Scraper utility tests
```

**48 tests** covering:
- API endpoints (9 tests) &mdash; CRUD operations, filtering, validation, error responses
- Price parsing (9 tests) &mdash; formats, edge cases, mojibake
- Date parsing (11 tests) &mdash; formats, invalid inputs, whitespace
- Scraper utilities (10 tests) &mdash; postcode extraction, normalization, reference resolution
- Formatting (9 tests) &mdash; price formatting, booleans, null markers

### Frontend

```bash
cd frontend
npx tsc --noEmit   # Type checking
npm run build       # Production build verification
```

### CI/CD

GitHub Actions runs on push and PR to `main`/`master`:
- **Backend:** Python 3.11, ruff lint, pytest
- **Frontend:** Node 20, TypeScript check, production build

---

## Configuration Reference

Configuration is loaded from environment variables (`.env` file supported via
python-dotenv). All values have sensible defaults.

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | string | `sqlite:///./rightmove.db` | SQLAlchemy database URL |
| `CORS_ORIGINS` | string | `http://localhost:5173,...` | Comma-separated allowed origins |
| `LOG_LEVEL` | string | `INFO` | Python logging level |
| `SCRAPER_REQUEST_TIMEOUT` | integer | `30` | HTTP request timeout in seconds |
| `SCRAPER_RETRY_ATTEMPTS` | integer | `3` | Max retry attempts per request |
| `SCRAPER_RETRY_BACKOFF` | float | `1.0` | Exponential backoff base in seconds |
| `SCRAPER_DELAY_BETWEEN_REQUESTS` | float | `0.5` | Delay between consecutive requests in seconds |
| `RATE_LIMIT_SCRAPE` | string | `5/minute` | Rate limit for `/scrape/*` endpoints |
| `RATE_LIMIT_DEFAULT` | string | `60/minute` | Default rate limit for all other endpoints |

---

## Project Structure

```
rightmove-api/
├── app/
│   ├── main.py              # FastAPI application, middleware, router mounting
│   ├── config.py            # Environment-based configuration
│   ├── database.py          # SQLAlchemy engine, session, migrations
│   ├── models.py            # Property and Sale ORM models
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── export.py            # Parquet export utilities
│   ├── parsing.py           # Price and date parsing functions
│   ├── feature_parser.py    # Key features extraction
│   ├── routers/
│   │   ├── scraper.py       # POST /scrape/* endpoints
│   │   ├── properties.py    # GET /properties, /postcodes, POST /export
│   │   └── analytics.py     # GET /analytics/* endpoints
│   └── scraper/
│       └── rightmove.py     # Rightmove HTTP client and Turbo Stream parser
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios client and TypeScript types
│   │   ├── charts/          # Recharts chart components (6 charts)
│   │   ├── components/      # UI components (SearchBar, PropertyCard, etc.)
│   │   ├── hooks/           # Custom hooks (usePostcodeSearch, useDarkMode)
│   │   ├── pages/           # Page components (SearchPage)
│   │   └── utils/           # Formatting, colors, chart theme utilities
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── tests/
│   ├── conftest.py          # Shared fixtures (in-memory DB, test client)
│   ├── test_api.py          # API integration tests
│   ├── test_parsing.py      # Parsing unit tests
│   └── test_scraper_utils.py # Scraper utility tests
├── scripts/                 # Data analysis and utility scripts
├── .github/workflows/ci.yml # CI pipeline
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies (pinned)
├── pytest.ini               # Pytest configuration
└── ruff.toml                # Ruff linter configuration
```

---

## Technical Details

**Turbo Stream parsing.** Rightmove uses React Router v7 with Turbo Stream data
format. Property data is embedded in `streamController.enqueue()` calls as a flat
JSON array with positional reference keys. The scraper decodes this format to extract
structured property and sale data.

**Upsert logic.** Properties are matched by address. Re-scraping updates fields only
when new data is non-empty, preserving existing data across scrapes.

**Parsed fields.** Prices and dates are stored in both raw format (`"£450,000"`,
`"15 Jun 2023"`) and parsed format (`450000`, `"2023-06-15"`) for analytics queries.
Backfill runs automatically on startup for existing data.

**Database migrations.** Schema changes are applied automatically on startup via
`ALTER TABLE` statements that silently no-op if the columns already exist.

**Frontend performance.** Long property lists use CSS `content-visibility: auto` for
deferred off-screen rendering (no JavaScript virtualization library needed). All chart
components are wrapped in `React.memo` to prevent unnecessary re-renders.

---

## Limitations

- Data availability depends on what Rightmove publishes on their house-prices pages.
- Scraping patterns (Turbo Stream format) may change if Rightmove updates their frontend.
- SQLite is single-writer &mdash; concurrent write-heavy workloads may need PostgreSQL.
- Area scraping depends on local Parquet postcode reference files in `data/postcodes/`.

---

## License

This project is for educational and personal use. Rightmove data is subject to their
terms of service.
