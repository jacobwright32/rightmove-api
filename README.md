# Rightmove House Prices API

A full-stack application for scraping, storing, enriching, and analyzing UK property sale data
from [Rightmove](https://www.rightmove.co.uk/house-prices.html). Combines a FastAPI
backend with a React frontend to provide on-demand data collection, multi-source enrichment,
ML price modelling, and interactive visualizations.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [External Data Sources](#external-data-sources)
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
  - [Enrichment](#enrichment)
  - [Modelling](#modelling)
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
| **Skip-existing** | Configurable freshness window skips recently-scraped postcodes to avoid redundant work |
| **Persistent storage** | SQLite database with upsert logic &mdash; re-scraping updates without duplicating |
| **Query & filter** | Search stored properties by postcode, type, bedrooms, with pagination |
| **Analytics** | Price trends, property type breakdowns, bedroom distributions, street comparisons, sales volume |
| **Market overview** | Database-wide statistics, recent sales, and cross-postcode comparisons |
| **Housing insights** | Investment dashboard with KPIs, scatter plots, deal detection, and postcode heatmaps |
| **Capital growth** | CAGR, volatility, max drawdown, Sharpe ratio, and linear price forecasting per postcode |
| **EPC enrichment** | Fetches Energy Performance Certificates with fuzzy address matching |
| **Crime data** | 12-month crime history per postcode with category breakdown and trends |
| **Flood risk** | Flood zone classification from Environment Agency open data |
| **Transport distances** | Distance to nearest rail, tube, bus, airport, and port via NaPTAN + cKDTree |
| **Planning applications** | Nearby planning applications from planning.data.gov.uk |
| **Listing status** | Checks if properties are currently listed on Rightmove |
| **ML modelling** | Train LightGBM/XGBoost models on 60+ features to predict prices, price/sqft, or price change % |
| **Interactive map** | Leaflet-based map view with clustered, colour-coded property markers |
| **Dark mode** | Full dark theme with reactive Recharts/Plotly chart theming |
| **Parquet export** | Export sales data to columnar Parquet files organized by outcode |
| **Rate limiting** | Configurable per-endpoint rate limits via slowapi |
| **Retry logic** | Exponential backoff with 429 handling for robust scraping |
| **CI/CD** | GitHub Actions pipeline with ruff linting, pytest, TypeScript checks, and frontend builds |

---

## Architecture

```
                                ┌─────────────────────┐
                                │   React Frontend    │
                                │ (Vite + Tailwind)   │
                                │  7 pages, Recharts  │
                                │  Plotly, Leaflet    │
                                └────────┬────────────┘
                                         │ /api/v1/*
                                         ▼
┌────────────┐    HTTP     ┌──────────────────────────────────┐
│  Rightmove │◄───────────►│        FastAPI Backend            │
│  (source)  │             │                                   │
└────────────┘             │  ┌──────────┐ ┌──────────────┐    │
                           │  │ Scraper  │ │  Analytics   │    │
┌────────────┐             │  │ Router   │ │   Router     │    │
│ External   │◄───────────►│  ├──────────┤ ├──────────────┤    │
│ APIs (6+)  │             │  │Enrichment│ │  Modelling   │    │
└────────────┘             │  │ Router   │ │   Router     │    │
                           │  └────┬─────┘ └──────┬───────┘    │
                           │       │              │            │
                           │       ▼              ▼            │
                           │  ┌────────────────────────────┐   │
                           │  │    SQLite (rightmove.db)   │   │
                           │  │ Property | Sale | Crime |  │   │
                           │  │       Planning             │   │
                           │  └────────────────────────────┘   │
                           └──────────────────────────────────┘
```

**Backend:** FastAPI, SQLAlchemy, SQLite, BeautifulSoup4, slowapi, LightGBM, XGBoost, scipy

**Frontend:** React 19, TypeScript, Vite 6, Tailwind CSS 4, Recharts, Plotly, Leaflet

---

## External Data Sources

The application integrates with multiple free, public data sources to enrich property records:

| Source | Auth Required | Data Provided | Caching |
|---|---|---|---|
| **[Rightmove](https://www.rightmove.co.uk/house-prices.html)** | None | Property sales, prices, addresses, features, floorplans | Stored in DB |
| **[EPC Register](https://epc.opendatacommunities.org/)** | Free API key | Energy ratings (A-G), EPC score, environment impact, energy cost | Stored on Property |
| **[Police API](https://data.police.uk/docs/)** | None | Monthly crime counts by category within 1 mile radius | `CrimeStats` table, 30-day TTL |
| **[Postcodes.io](https://postcodes.io/)** | None | Postcode geocoding (lat/lng), used by crime + transport enrichment | Stored on Property |
| **[NaPTAN](https://naptan.api.dft.gov.uk/)** | None | ~350k UK public transport stop locations (rail, tube, tram, bus) | Parquet cache, 90-day refresh |
| **[Environment Agency](https://environment.data.gov.uk/)** | None | Flood risk zones and active flood warnings | Stored on Property |
| **[Planning Data](https://www.planning.data.gov.uk/)** | None | Nearby planning applications (submitted/approved/refused) | `PlanningApplication` table, 30-day TTL |

Static data (no API calls): **25 UK airports** and **20 major ports** with coordinates, embedded in `app/enrichment/transport.py`.

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
available at `/docs` when the server is running. **34 endpoints** across 5 routers.

### Scraping

#### `POST /api/v1/scrape/postcode/{postcode}`

Scrape properties for a UK postcode.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_properties` | integer | `50` | Maximum properties to extract (1&ndash;500) |
| `pages` | integer | `1` | Listing pages to scrape (1&ndash;50) |
| `link_count` | integer | *null* | Detail pages to visit. `null` = fast mode, `0` = all |
| `floorplan` | boolean | `false` | Extract floorplan image URLs |
| `extra_features` | boolean | `false` | Extract key features list |
| `save_parquet` | boolean | `false` | Save each property to Parquet as it's scraped |
| `skip_existing` | boolean | `true` | Skip postcodes scraped within freshness window |
| `force` | boolean | `false` | Force re-scrape even if fresh data exists |

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

---

#### `POST /api/v1/scrape/area/{partial}`

Scrape all postcodes matching a partial postcode prefix.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `pages` | integer | `1` | Listing pages per postcode (1&ndash;50) |
| `link_count` | integer | *null* | Detail pages per postcode |
| `max_postcodes` | integer | `0` | Maximum postcodes to scrape (`0` = all) |
| `floorplan` | boolean | `false` | Extract floorplan image URLs |
| `extra_features` | boolean | `false` | Extract key features list |
| `save_parquet` | boolean | `false` | Save each property to Parquet |
| `skip_existing` | boolean | `true` | Skip recently-scraped postcodes |
| `force` | boolean | `false` | Force re-scrape all postcodes |

**Response:**

```json
{
  "message": "Scraped 5 postcodes in area SW20",
  "postcodes_scraped": ["SW20 8NE", "SW20 8NY", "SW20 8ND"],
  "postcodes_failed": [],
  "postcodes_skipped": ["SW20 0HG"],
  "total_properties": 142
}
```

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

---

### Properties

#### `GET /api/v1/properties`

List stored properties with optional filters.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `postcode` | string | *null* | Filter by postcode (partial match) |
| `property_type` | string | *null* | Filter by property type |
| `min_bedrooms` | integer | *null* | Minimum bedrooms |
| `max_bedrooms` | integer | *null* | Maximum bedrooms |
| `skip` | integer | `0` | Pagination offset |
| `limit` | integer | `0` | Maximum results (`0` = all) |

#### `GET /api/v1/properties/{property_id}`

Get a single property with full sale history, EPC, transport, flood, and listing data.

#### `GET /api/v1/properties/{property_id}/similar`

Find similar properties by type, bedrooms, location, and price range.

#### `GET /api/v1/properties/geo`

Get properties with lat/lng coordinates for map display. Batch-geocodes via Postcodes.io if coordinates are missing.

#### `GET /api/v1/properties/postcode/{postcode}/status`

Check whether data exists for a postcode and when it was last updated.

---

### Postcodes

#### `GET /api/v1/postcodes`

List all scraped postcodes with property counts.

#### `GET /api/v1/postcodes/suggest/{partial}`

Autocomplete postcodes from a partial input. Checks both the database and Rightmove.

---

### Analytics

All postcode analytics endpoints are under `/api/v1/analytics/postcode/{postcode}`.

| Endpoint | Description |
|---|---|
| `GET .../price-trends` | Monthly average, median, min, max prices |
| `GET .../property-types` | Count and average price per property type |
| `GET .../bedroom-distribution` | Count and average price per bedroom count |
| `GET .../street-comparison` | Average price per street |
| `GET .../postcode-comparison` | Average price per full postcode |
| `GET .../sales-volume` | Number of sales per year |
| `GET .../summary` | **All of the above in a single call** |
| `GET .../growth` | Capital growth metrics: CAGR (1/3/5/10yr), volatility, max drawdown, Sharpe ratio, linear forecast with confidence bands |
| `GET .../crime` | 12-month crime statistics from Police API (pie/bar/trend data) |
| `GET .../flood-risk` | Flood zone classification + active warnings from Environment Agency |
| `GET .../planning` | Nearby planning applications from planning.data.gov.uk |

**Market-wide endpoints:**

| Endpoint | Description |
|---|---|
| `GET /api/v1/analytics/market-overview` | Database-wide stats: postcode count, property count, total sales, average price, recent sales table, price trends |
| `GET /api/v1/analytics/housing-insights` | Investment dashboard: price distribution, time series, scatter with trend line, postcode heatmap, KPIs, top deals |
| `GET /api/v1/analytics/growth-leaderboard` | Top postcodes ranked by CAGR over specified period |

---

### Enrichment

Enrichment endpoints fetch data from external APIs and store results on Property records.

| Endpoint | External API | Description |
|---|---|---|
| `POST /api/v1/enrich/epc/{postcode}` | EPC Register | Fetch energy certificates, fuzzy-match to properties by address |
| `POST /api/v1/enrich/transport/{postcode}` | NaPTAN (cached) | Compute distances to nearest rail, tube, tram, bus, airport, port via cKDTree |
| `POST /api/v1/enrich/listing/{postcode}` | Rightmove | Check current listing status for all properties in postcode |
| `GET /api/v1/properties/{property_id}/listing` | Rightmove | Get listing status for a single property |

**Transport enrichment details:**

Distances are computed offline using scipy `cKDTree` — zero API calls at query time.
NaPTAN data (~350k stops) is downloaded once and cached as parquet. Properties without
coordinates are auto-geocoded via Postcodes.io before distance computation.

Returns: `dist_nearest_rail_km`, `dist_nearest_tube_km`,
`dist_nearest_bus_km`, `dist_nearest_airport_km`, `dist_nearest_port_km`,
`nearest_rail_station`, `nearest_tube_station`, `nearest_airport`, `nearest_port`, `bus_stops_within_500m`.

---

### Modelling

Train and use ML models for property price prediction. Models are stored in-memory
(lost on server restart).

| Endpoint | Description |
|---|---|
| `GET /api/v1/model/features` | List available features (60+), targets, and dataset size |
| `POST /api/v1/model/train` | Train a LightGBM or XGBoost model with configurable features, target, split, and hyperparameters |
| `GET /api/v1/model/{model_id}/predict` | Predict target for a single property (with optional prediction date) |
| `GET /api/v1/model/{model_id}/predict-postcode` | Predict for all properties in a postcode |

**Training request body:**

```json
{
  "target": "price_numeric",
  "features": ["bedrooms", "bathrooms", "latitude", "longitude", "dist_nearest_rail_km"],
  "model_type": "lightgbm",
  "split_type": "random",
  "test_size": 0.2,
  "log_transform": false,
  "hyperparameters": {}
}
```

**Available targets:** `price_numeric` (Sale Price), `price_per_sqft` (Price per Sq Ft), `price_change_pct` (Price Change %)

**Feature categories:** Property Basics, EPC, Location, Transport (10 features), Crime (6 features), Parsed Features (20+ from key features), Sale Context

**Metrics returned:** R-squared, RMSE, MAE, MAPE, feature importances, worst predictions

---

### Export

#### `POST /api/v1/export/{postcode}`

Export all sales data for a postcode to Parquet files, organized by outcode.

---

### Health

#### `GET /health`

Health check endpoint with database connectivity verification.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "ok"
}
```

---

## Data Model

### Property

| Column Group | Columns |
|---|---|
| **Core** | `id`, `address` (unique), `postcode` (indexed), `property_type`, `bedrooms`, `bathrooms`, `extra_features` (JSON), `floorplan_urls` (JSON), `url` |
| **EPC** | `epc_rating`, `epc_score`, `epc_environment_impact`, `estimated_energy_cost` |
| **Flood** | `flood_risk_level` |
| **Listing** | `listing_status`, `listing_price`, `listing_price_display`, `listing_date`, `listing_url`, `listing_checked_at` |
| **Geo** | `latitude`, `longitude` |
| **Transport** | `dist_nearest_rail_km`, `dist_nearest_tube_km`, `dist_nearest_bus_km`, `dist_nearest_airport_km`, `dist_nearest_port_km`, `nearest_rail_station`, `nearest_tube_station`, `nearest_airport`, `nearest_port`, `bus_stops_within_500m` |
| **Timestamps** | `created_at`, `updated_at` |

### Sale

| Column | Type | Description |
|---|---|---|
| `id` | integer | PK |
| `property_id` | integer | FK &rarr; Property |
| `date_sold` | string | e.g., "15 Jun 2023" |
| `price` | string | e.g., "£450,000" |
| `price_numeric` | integer | Parsed integer price in GBP |
| `date_sold_iso` | string | ISO 8601 date (YYYY-MM-DD) |
| `price_change_pct` | string | Percentage change from prior sale |
| `property_type` | string | Type at time of sale |
| `tenure` | string | FREEHOLD or LEASEHOLD |

**Unique constraint:** `(property_id, date_sold, price)` &mdash; prevents duplicate sale records

### CrimeStats

| Column | Type | Description |
|---|---|---|
| `postcode` | string | UK postcode (indexed) |
| `month` | string | YYYY-MM format |
| `category` | string | Crime category (e.g., "burglary", "anti-social-behaviour") |
| `count` | integer | Number of incidents |
| `fetched_at` | datetime | Cache timestamp (30-day TTL) |

### PlanningApplication

| Column | Type | Description |
|---|---|---|
| `postcode` | string | UK postcode (indexed) |
| `reference` | string | Application reference number |
| `description` | string | Application description |
| `status` | string | submitted / approved / refused |
| `decision_date` | string | Decision date |
| `application_type` | string | householder / full / outline / listed-building |
| `is_major` | boolean | Flagged if 10+ dwellings or commercial |
| `fetched_at` | datetime | Cache timestamp (30-day TTL) |

---

## Frontend

The React frontend provides 7 pages with interactive charts, dark mode, and enrichment controls.

### Pages

| Page | Route | Description |
|---|---|---|
| **Search** | `/` | Postcode search, scrape controls, analytics dashboard, property list |
| **Market Overview** | `/market` | Database-wide statistics, recent sales table, cross-postcode trends |
| **Compare Areas** | `/compare` | Side-by-side multi-postcode charts and metrics |
| **Property Detail** | `/property/:id` | Full property view with sale history, EPC badge, crime/flood/transport/planning sections, listing status, similar properties |
| **Housing Insights** | `/insights` | Investment dashboard: histogram, time series, scatter with trend line, heatmap, KPIs, deal detection |
| **Map View** | `/map` | Leaflet map with clustered markers, colour-coded by price range |
| **Modelling** | `/modelling` | Train ML models, view metrics, feature importance, scatter/residual plots, single/postcode predictions |

### Key Components

- **TransportSection** &mdash; Grid showing distances to nearest rail, tube, bus, airport, port with station/port names. "Compute" button triggers enrichment.
- **CrimeSection** &mdash; Pie chart (category breakdown), horizontal bar (top categories), monthly trend line
- **FloodRiskSection** &mdash; Flood zone badge with explanation text
- **EPCBadge** &mdash; Colour-coded A-G rating with score details
- **PlanningSection** &mdash; Table of nearby planning applications with status badges
- **GrowthSection** &mdash; CAGR badges, forecast chart with confidence bands
- **ListingStatusSection** &mdash; Current listing status with price and link

---

## Testing

### Backend

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_api.py -v            # API integration tests
pytest tests/test_parsing.py -v        # Price/date parsing tests
pytest tests/test_scraper_utils.py -v  # Scraper utility tests
pytest tests/test_modelling.py -v      # ML modelling tests
pytest tests/test_transport.py -v      # Transport enrichment tests
```

**109 tests** covering:
- **API endpoints** (9 tests) &mdash; CRUD operations, filtering, validation, error responses
- **Price parsing** (9 tests) &mdash; formats, edge cases, mojibake
- **Date parsing** (11 tests) &mdash; formats, invalid inputs, whitespace
- **Scraper utilities** (10 tests) &mdash; postcode extraction, normalization, reference resolution
- **Formatting** (9 tests) &mdash; price formatting, booleans, null markers
- **Market overview** (4 tests) &mdash; empty DB, with data, recent sales, price trends
- **Housing insights** (3 tests) &mdash; empty DB, with data, filters
- **Modelling** (12 tests) &mdash; feature listing, validation, LightGBM/XGBoost training, temporal/random splits, prediction
- **Transport** (14 tests) &mdash; haversine math, cartesian conversion, static data validation, endpoint, ML feature registry
- **Other** (28 tests) &mdash; similar properties, postcode status, EPC, crime, flood, planning endpoints

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
| `SCRAPER_DELAY_BETWEEN_REQUESTS` | float | `0.25` | Delay between consecutive requests in seconds |
| `SCRAPER_FRESHNESS_DAYS` | integer | `7` | Days before a postcode is considered stale |
| `RATE_LIMIT_SCRAPE` | string | `30/minute` | Rate limit for `/scrape/*` endpoints |
| `RATE_LIMIT_DEFAULT` | string | `60/minute` | Default rate limit for all other endpoints |
| `EPC_API_EMAIL` | string | *empty* | EPC Register API email (free registration) |
| `EPC_API_KEY` | string | *empty* | EPC Register API key |
| `NAPTAN_MAX_AGE_DAYS` | integer | `90` | Days before NaPTAN transport data is re-downloaded |

---

## Project Structure

```
rightmove-api/
├── app/
│   ├── main.py              # FastAPI application, middleware, SPA fallback, router mounting
│   ├── config.py            # Environment-based configuration
│   ├── database.py          # SQLAlchemy engine, session, auto-migrations
│   ├── models.py            # Property, Sale, CrimeStats, PlanningApplication ORM models
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── export.py            # Parquet export utilities
│   ├── parsing.py           # Price and date parsing functions
│   ├── feature_parser.py    # Key features extraction (20+ parsed fields)
│   ├── routers/
│   │   ├── scraper.py       # POST /scrape/* endpoints (fast/slow, skip_existing/force)
│   │   ├── properties.py    # GET /properties, /postcodes, /geo, POST /export
│   │   ├── analytics.py     # GET /analytics/* (trends, growth, crime, flood, planning)
│   │   ├── enrichment.py    # POST /enrich/* (EPC, transport, listing)
│   │   └── modelling.py     # GET/POST /model/* (features, train, predict)
│   ├── enrichment/
│   │   ├── epc.py           # EPC Register API service
│   │   ├── crime.py         # Police API + Postcodes.io geocoding
│   │   ├── transport.py     # NaPTAN data + cKDTree distance computation
│   │   ├── listing.py       # Rightmove listing status checker
│   │   └── geocoding.py     # Postcodes.io geocoding helper
│   ├── modelling/
│   │   ├── data_assembly.py # Feature registry (60+), dataset building from DB
│   │   ├── trainer.py       # LightGBM/XGBoost training with metrics
│   │   └── predictor.py     # Single-property and postcode prediction
│   └── scraper/
│       └── rightmove.py     # Rightmove HTTP client and Turbo Stream parser
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios client and TypeScript types
│   │   ├── charts/          # Recharts chart components (6 charts)
│   │   ├── components/      # UI components (18 components)
│   │   ├── hooks/           # Custom hooks (usePostcodeSearch, useDarkMode)
│   │   ├── pages/           # Page components (7 pages)
│   │   └── utils/           # Formatting, colors, chart theme utilities
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── tests/
│   ├── conftest.py          # Shared fixtures (in-memory DB, test client)
│   ├── test_api.py          # API integration tests
│   ├── test_parsing.py      # Parsing unit tests
│   ├── test_scraper_utils.py # Scraper utility tests
│   ├── test_modelling.py    # ML modelling tests
│   └── test_transport.py    # Transport enrichment tests
├── data/                    # Cached data (NaPTAN parquet, gitignored)
├── scripts/                 # Data analysis and utility scripts
├── tasks/                   # Task tracker and lessons learned
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
when new data is non-empty, preserving existing data across scrapes. Duplicate sales
are handled with a savepoint-based safety net (`db.begin_nested()` + `IntegrityError` catch).

**Parsed fields.** Prices and dates are stored in both raw format (`"£450,000"`,
`"15 Jun 2023"`) and parsed format (`450000`, `"2023-06-15"`) for analytics queries.
Backfill runs automatically on startup for existing data.

**Database migrations.** Schema changes are applied automatically on startup via
`ALTER TABLE` statements that silently no-op if the columns already exist.

**Transport distance computation.** NaPTAN CSV data (~96MB, ~350k stops) is downloaded
once and cached as parquet (~15MB). Stop types are split into rail (RSE), tube (TMU),
and bus (BCT). Coordinates are converted to
3D unit-sphere Cartesian for scipy `cKDTree` nearest-neighbour lookup (O(log n)). Final
distances use exact haversine formula. Bus stops within 500m use `query_ball_point`.

**ML pipeline.** Features are assembled from Property + Sale + CrimeStats tables plus
parsed key features (20+ boolean/numeric/categorical fields from free-text descriptions).
Models train in-memory with LightGBM or XGBoost, supporting random or temporal train/test
splits and optional log-transform of the target variable.

**Frontend performance.** Long property lists use CSS `content-visibility: auto` for
deferred off-screen rendering. All chart components are wrapped in `React.memo`. The
SPA uses a FastAPI catch-all that serves `index.html` for non-API routes.

---

## Limitations

- Data availability depends on what Rightmove publishes on their house-prices pages.
- Scraping patterns (Turbo Stream format) may change if Rightmove updates their frontend.
- SQLite is single-writer &mdash; concurrent write-heavy workloads may need PostgreSQL.
- ML models are stored in-memory and lost on server restart.
- EPC enrichment requires a free API key from epc.opendatacommunities.org.
- NaPTAN data download is ~96MB on first transport enrichment request.

---

## License

This project is for educational and personal use. Rightmove data is subject to their
terms of service.
