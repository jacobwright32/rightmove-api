# Codebase Reference (auto-generated 2026-02-12)
# Condensed snapshot of every file, endpoint, model, and component.

## Stack
Python 3.9.12 | FastAPI | SQLAlchemy | SQLite | BeautifulSoup4 | LightGBM/XGBoost
React 19 | TypeScript 5.7 | Vite 6 | Tailwind CSS 4 | Recharts | Plotly | Leaflet | Axios

## Database Tables (app/models.py)

### Property (58 cols)
Core: id(PK), address(UNIQUE), postcode(idx), property_type, bedrooms, bathrooms, extra_features(JSON), floorplan_urls(JSON), url
EPC: epc_rating, epc_score, epc_environment_impact, estimated_energy_cost
Flood: flood_risk_level (very_low|low|medium|high)
Listing: listing_status, listing_price, listing_price_display, listing_date, listing_url, listing_checked_at
Geo: latitude, longitude
Transport: dist_nearest_{rail,tube,tram,bus,airport,port}_km, nearest_{rail_station,tube_station,airport,port}, bus_stops_within_500m
Timestamps: created_at, updated_at
Indexes: (postcode,created_at), (property_type,bedrooms)
Rel: sales (one-to-many, cascade delete)

### Sale (8 cols)
id(PK), property_id(FK,idx), date_sold, price, price_numeric(idx), date_sold_iso(idx), price_change_pct, property_type, tenure
UNIQUE(property_id, date_sold, price) -- handled via savepoint
Indexes: (property_id,date_sold_iso), (property_id,price_numeric), (date_sold_iso,price_numeric)

### CrimeStats (6 cols)
id(PK), postcode(idx), month(YYYY-MM), category(idx), count, fetched_at
UNIQUE(postcode, month, category) | Indexes: (category,postcode), (postcode,fetched_at)

### PlanningApplication (7 cols)
id(PK), postcode(idx), reference, description, status, decision_date, application_type, is_major(0/1), fetched_at
UNIQUE(postcode, reference) | Index: (postcode,fetched_at)

## Config (app/config.py)
All env-driven via python-dotenv + _read_secret() fallback to secrets/ dir.
DATABASE_URL=sqlite:///./rightmove.db | CORS_ORIGINS=localhost:5173
SCRAPER_REQUEST_TIMEOUT=30s | SCRAPER_RETRY_ATTEMPTS=3 | SCRAPER_DELAY=0.25s | SCRAPER_FRESHNESS_DAYS=7
RATE_LIMIT_SCRAPE=30/min | RATE_LIMIT_DEFAULT=60/min
EPC_API_EMAIL, EPC_API_KEY (from secrets or env)
LISTING_FRESHNESS_HOURS=24 | NAPTAN_MAX_AGE_DAYS=90 | CRIME_API_DELAY=0.125s

## Backend Files

### app/main.py
FastAPI app init, CORS middleware, mounts 5 routers under /api/v1/, serves frontend dist, SPA catch-all with API guard.

### app/database.py
engine + SessionLocal + get_db() dependency. _migrate_db() runs 27 ALTER TABLE migrations on startup. _backfill_parsed_fields() populates price_numeric/date_sold_iso.

### app/schemas.py
50+ Pydantic v2 models. Key: PropertyBrief, PropertyDetail, PropertyGeoPoint, SaleOut, ScrapeResponse, AreaScrapeResponse, MarketOverview, PostcodeAnalytics, HousingInsightsResponse, PostcodeGrowthResponse, GrowthLeaderboardEntry, EPCEnrichmentResponse, TransportEnrichmentResponse, FloodRiskResponse, CrimeSummaryResponse, PlanningResponse, PropertyListingResponse, AvailableFeaturesResponse, TrainRequest, TrainResponse, SinglePredictionResponse, PostcodePredictionResponse, CoverageResponse, BulkEnrichmentStatus.

### app/parsing.py
parse_price_to_int("£450,000") -> 450000 | parse_date_to_iso("4 Nov 2023") -> "2023-11-04"

### app/feature_parser.py
parse_all_features(extra_features_json) -> dict of 40+ parsed fields.
Parsers: epc_rating, council_tax_band, chain_free, parking, garden, heating, lease_years, sq_ft, service_charge, ground_rent, furnished, floor_level, etc.

### app/export.py
save_property_parquet(prop) -> sales_data/{OUTCODE}/{address}.parquet (PyArrow, Snappy compression)

### app/scraper/rightmove.py
Turbo Stream parser for Rightmove React Router v7 data.
_parse_turbo_stream(html) -> flat array | _resolve_ref/object/list for reference resolution
_extract_properties_from_stream() | _listing_dict_to_property() -> PropertyData
Fast path: scrape_postcode_from_listing() - single HTTP per page, latest transaction only
Slow path: scrape_postcode_with_details() - visits detail pages, full history + features + floorplans
get_single_house_details(url) - single property detail page
Data classes: PropertyData(address,postcode,property_type,bedrooms,bathrooms,extra_features,floorplan_urls,url,sales) + SaleRecord
_request_with_retry() - exponential backoff, User-Agent spoofing

## API Endpoints (app/routers/)

### scraper.py (3 endpoints)
POST /scrape/postcode/{postcode} - params: max_properties(1-500), pages(1-50), link_count, floorplan, extra_features, save_parquet, skip_existing(default True), force. Uses _is_postcode_fresh() + _upsert_property() with savepoint for dupes.
POST /scrape/area/{partial} - batch scrape from ONS postcode parquet files (data/postcodes/{OUTCODE}.parquet). Tracks success/skip/fail per postcode.
POST /scrape/property - body: {url, floorplan}. Single property scrape by URL (validates rightmove.co.uk domain).

### properties.py (7 endpoints)
GET /properties - filter: postcode, property_type, min/max_bedrooms, skip, limit. Eager loads sales.
GET /properties/geo - returns PropertyGeoPoint[] with lat/lng. Batch geocodes missing via Postcodes.io.
GET /properties/{id} - single property with all sales
GET /properties/{id}/similar - same outcode + type + ±1 bed, ordered by closest price (limit 1-20)
GET /properties/postcode/{postcode}/status - has_data, property_count, last_updated
GET /postcodes/suggest/{partial} - autocomplete from DB + Rightmove
GET /postcodes - all scraped postcodes with counts
POST /export/{postcode} - export to parquet

### analytics.py (5 endpoints)
GET /analytics/market-overview - totals, price stats, distributions, top postcodes, yearly trends, monthly trends, 50 recent sales
GET /analytics/postcode/{postcode} - price_trends, property_types, street_comparison, postcode_comparison, bedroom_dist, sales_volume
GET /analytics/housing-insights - 15+ filter params, single-pass aggregation: histogram(20 buckets), time_series, scatter(2000 cap), postcode_heatmap, KPIs(appreciation, price_per_bedroom, market_velocity, volatility), investment_deals(value_score)
GET /analytics/postcode/{postcode}/growth - CAGR(3/5/10yr), volatility, max_drawdown, forecast(polynomial/exponential), annual_medians
GET /analytics/growth-leaderboard - top postcodes by CAGR

### enrichment.py (10+ endpoints via nested routers)
POST /enrich/epc/{postcode} - EPC API (opendatacommunities.org), fuzzy address match, updates 4 cols
POST /enrich/transport/{postcode} - NaPTAN + static airports/ports, cKDTree, updates 10 cols
POST /enrich/listing/{postcode} - Rightmove for-sale status check
GET /analytics/postcode/{postcode}/crime - Police API, 5yr history, 30-day cache
GET /analytics/postcode/{postcode}/flood-risk - EA API, risk zones + active warnings
GET /analytics/postcode/{postcode}/planning - planning.data.gov.uk, 30-day cache, major detection
GET /properties/{id}/listing - single property listing status (24hr cache)
GET /enrich/bulk/coverage - feature coverage stats (% complete per type)
GET /enrich/bulk/status - current bulk enrichment progress
POST /enrich/bulk/start - spawn background enrichment thread (types, delay params)
POST /enrich/bulk/stop - stop running enrichment

### modelling.py (4 endpoints)
GET /model/features - FEATURE_REGISTRY (60+ features by category) + TARGETS + property count
POST /model/train - body: target, features[], model_type(lightgbm|xgboost), split_strategy(random|temporal), split_params, hyperparameters, log_transform. Returns model_id, metrics(R²,RMSE,MAE,MAPE), feature_importances, predictions, train/test_size.
GET /model/{id}/predict?property_id=N&prediction_date=YYYY-MM - single property prediction
GET /model/{id}/predict-postcode?postcode=X&limit=50 - batch postcode predictions with last_sale comparison

## Enrichment Services (app/enrichment/)

### epc.py
fetch_epc_for_postcode() -> EPC API (Basic auth), returns [{address, epc_rating, epc_score, environment_impact, estimated_energy_cost}]

### crime.py
get_crime_summary(db, postcode) -> Police API + Postcodes.io geocoding. 5yr history (60 months), CRIME_API_DELAY between requests. 30-day cache in CrimeStats table.

### transport.py
NaPTAN CSV (~96MB) -> parquet cache. Static: 25 airports + 20 ports. scipy cKDTree per stop type (RSE=rail, TMU=tube, BCT=bus). compute_transport_distances(lat,lon) -> 6 distances + 4 names + bus count. _haversine_km() for final distances. enrich_postcode_transport() orchestrates geocoding + distance computation.

### flood.py
get_flood_risk(postcode) -> EA Flood Monitoring API (warnings) + EA Flood Areas API (zones). Risk levels: very_low/low/medium/high/unknown. Caches on Property.flood_risk_level.

### planning.py
fetch_planning_applications(lat,lng) -> planning.data.gov.uk API. _parse_application_type() from reference codes. _is_major_development() keyword detection. 30-day cache in PlanningApplication table.

### listing.py
_extract_listing_from_detail_page(url) -> Turbo Stream parsing for propertyListing status. check_property_listing(db, property_id) with 24hr freshness. Updates listing_* columns.

### geocoding.py
geocode_postcode() -> Postcodes.io single. batch_geocode_postcodes() -> POST batch API (100 per chunk).

### bulk.py
Background thread orchestrator. start(types, delay) | stop() | get_status() | get_coverage(). Types: geocode, transport, epc, crime, flood, planning.

## ML Pipeline (app/modelling/)

### data_assembly.py
FEATURE_REGISTRY: 60+ features in categories — Property Basics(3), EPC(4), Location(3), Transport(10), Crime(6), Parsed Features(40+), Sale Context(4).
TARGETS: price_numeric, price_per_sqft, price_change_pct.
assemble_dataset(db, target, features) -> DataFrame. Joins Sale+Property, loads crime by postcode (time-matched: 12mo trailing from sale date), parses extra_features, builds categorical columns.

### trainer.py
train_model() -> LightGBM or XGBoost (100 rounds default). Random (70/30) or temporal split. Optional log_transform (log1p/expm1). Metrics: R², RMSE, MAE, MAPE (no sklearn). In-memory _model_store[uuid].

### predictor.py
predict_single(model_id, db, property_id) | predict_postcode(model_id, db, postcode, limit) with last_sale comparison.

## Frontend Structure (frontend/src/)

### Routes (App.tsx)
/ -> SearchPage | /market -> MarketOverviewPage | /compare -> CompareAreasPage
/insights -> HousingInsightsPage | /map -> MapViewPage(lazy) | /model -> ModellingPage(lazy)
/enrich -> EnrichmentPage(lazy) | /property/:id -> PropertyDetailPage

### Pages (7)
SearchPage - postcode search + scrape controls + AnalyticsDashboard + PropertyList
PropertyDetailPage - full property view: listing status, price appreciation, price history chart, features, floorplans, EPC, sale history, growth, flood, transport, planning, crime, similar properties
MarketOverviewPage - 6 stat cards, price distribution, trends, property types, bedrooms, yearly volume, top postcodes table, growth leaderboard, 50 recent sales
CompareAreasPage - PostcodeMultiInput(max 4), overlaid price trends, grouped bars, sales volume comparison
HousingInsightsPage - 15+ filters, KPI cards(8), Plotly charts(histogram, time series, scatter+trendline, postcode heatmap), investment deals table (sortable)
ModellingPage - sidebar(target, model, split, log transform, hyperparams, feature selection by category) + results(metrics, feature importance, pred vs actual scatter, residual histogram, worst predictions, single prediction, postcode batch prediction)
EnrichmentPage - coverage table with progress bars, bulk enrichment controls(type checkboxes, delay slider, start/stop), log panel(autoscroll)

### Components (20+)
NavBar - 7 nav links, ThemeToggle, Reset DB button (2-step confirm)
SearchBar - autocomplete(400ms debounce), scrape options grid(pages, link_count, max_postcodes, floorplan, features, parquet, force)
PropertyCard - expandable: header(address, meta, EPCBadge, FloodRiskBadge) + expanded(features, floorplans, SaleHistoryTable, detail link)
AnalyticsDashboard(memo) - stat cards + 6 charts + PropertyList
StatCard(memo) - large number + label
LoadingOverlay - spinner + state-specific message (checking/scraping/loading)
ThemeToggle - sun/moon, localStorage persistence, system pref detection
PostcodeMultiInput - chip input with suggestions, max N
EPCBadge - A-G color-coded (green-red gradient), sm|md sizes
FloodRiskBadge - risk level color + droplet icon
TransportSection - 5 card grid (distances + names), enrichment button
CrimeSection - Recharts: pie(categories), horizontal bar(top 7), trend line(monthly)
GrowthSection - CAGR badges(1/3/5yr), volatility, drawdown, historical+forecast AreaChart
FloodRiskSection - risk badge, zone explanation, active warnings
PlanningSection - status badges, major filter toggle, scrollable cards
ListingStatusSection - status badge, price, date, Rightmove link, freshness
SaleHistoryTable - date|price|change%|tenure

### Charts (6, all memo'd)
PriceTrendChart(LineChart) - avg/median/max price by month
PropertyTypeChart(PieChart+BarChart) - count + avg price by type
BedroomDistribution(BarChart) - dual Y-axis: count + avg price
SalesVolumeTimeline(AreaChart) - yearly sales count with gradient
PriceHeatmap - top 20 streets, color intensity by avg price
PostcodeHeatmap - all postcodes, color intensity by avg price

### Hooks
usePostcodeSearch - state machine (idle->scraping->loading->done/error), AbortController, Promise.allSettled
useDarkMode - MutationObserver on <html> classList via useSyncExternalStore

### API Client (api/client.ts)
Axios baseURL="/api/v1". 39 functions covering: scraping(3), properties(6), analytics(5), enrichment(7), modelling(4), bulk(4), admin(1), export(1).

### Utils
formatting.ts - formatPrice(abbreviated), formatPriceFull, normalisePostcode
chartTheme.ts - getChartColors(dark) -> grid/axis/tooltip/text colors
colors.ts - getColorIntensity(value,min,max) -> Tailwind color class

## External APIs
Rightmove (no auth) - property sales, prices, features, floorplans, listing status
EPC Register (free key, Basic auth) - energy certificates
Police API (no auth) - crime data by lat/lng+month
Postcodes.io (no auth) - geocoding, batch geocoding
NaPTAN (no auth) - ~350k UK transport stops (CSV download)
Environment Agency (no auth) - flood monitoring + flood areas
planning.data.gov.uk (no auth) - planning applications

## Infrastructure
CI: GitHub Actions (Python 3.11 ruff+pytest, Node 20 tsc+build)
Rate limiting: slowapi (30/min scrape, 60/min default)
Auto-migrations: 27 ALTER TABLE on startup (no Alembic)
SPA: catch-all serves index.html, API guard for /api/ prefix
Dark mode: CSS class on <html>, localStorage, useDarkMode hook, getChartColors()
Tests: 109 passing (conftest.py: in-memory SQLite + TestClient)

## File Map
app/main.py, app/config.py, app/database.py, app/models.py, app/schemas.py, app/parsing.py, app/feature_parser.py, app/export.py
app/scraper/rightmove.py
app/routers/{scraper,properties,analytics,enrichment,modelling}.py
app/enrichment/{epc,crime,transport,flood,planning,listing,geocoding,bulk}.py
app/modelling/{data_assembly,trainer,predictor}.py
frontend/src/App.tsx, main.tsx, index.css, vite-env.d.ts, plotly.d.ts
frontend/src/pages/{Search,PropertyDetail,MarketOverview,CompareAreas,HousingInsights,Modelling,Enrichment}Page.tsx + MapViewPage.tsx
frontend/src/components/{NavBar,SearchBar,PropertyCard,PropertyList,AnalyticsDashboard,StatCard,LoadingOverlay,ThemeToggle,PostcodeMultiInput,EPCBadge,FloodRiskBadge,TransportSection,CrimeSection,GrowthSection,FloodRiskSection,PlanningSection,ListingStatusSection,SaleHistoryTable}.tsx
frontend/src/charts/{PriceTrend,PropertyType,BedroomDistribution,SalesVolumeTimeline,PriceHeatmap,PostcodeHeatmap}Chart.tsx
frontend/src/hooks/{usePostcodeSearch,useDarkMode}.ts
frontend/src/utils/{formatting,chartTheme,colors}.ts
frontend/src/api/{client,types}.ts
tests/{conftest,test_api,test_parsing,test_scraper_utils,test_modelling,test_transport}.py
2