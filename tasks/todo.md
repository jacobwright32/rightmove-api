# UK House Prices - Task Tracker

## Current Session
_Session started: 2026-02-10_

### Completed
**Critical:**
- [x] Fix .gitignore (added node_modules, parquet, sales_data, frontend/dist, OS files, pytest cache)
- [x] Pin dependency versions (requirements.txt with version ranges)
- [x] Environment-based config (app/config.py + .env.example + python-dotenv)
- [x] Add rate limiting to scrape endpoints (slowapi, 5/min on scrape routes)
- [x] Scraper retry logic with exponential backoff (_request_with_retry + delays between requests)
- [x] Set up test infrastructure (pytest + 48 tests: parsing, scraper utils, API integration)

**High:**
- [x] Fix silent exception swallowing (specific exceptions, failed_postcodes in response)
- [x] Add request cancellation (AbortController + Promise.allSettled in hook)
- [x] Frontend accessibility (ARIA labels, button for expandable, scope on th, lazy images, empty state)
- [x] Clean up orphaned files (deleted rightmove2/3.db, root package-lock.json)
- [x] CI/CD pipeline (GitHub Actions workflow, ruff linting config)

**Medium:**
- [x] Add missing DB indexes (price_numeric, date_sold_iso, composite property+date)
- [x] Extract duplicated scrape logic to _scrape_postcode_properties() helper
- [x] Memoize all chart components (React.memo on all 6 charts)
- [x] Break up SearchPage (extracted AnalyticsDashboard, StatCard components)
- [x] Extract shared color utils (getColorIntensity -> utils/colors.ts)

**Low (previously backlog — completed):**
- [x] Health check endpoint (`/health` with DB connectivity check)
- [x] API versioning (all routers under `/api/v1/`, frontend client updated)
- [x] Dark mode support (ThemeToggle component, dark: classes on all components, Recharts chart dark mode via useDarkMode hook + chartTheme utils)
- [x] Optimize property list rendering (CSS `content-visibility: auto` per react-best-practices skill)

**Bug fix (session 2):**
- [x] Fix 7 failing API tests (URL prefix mismatch after /api/v1/ migration)

**New pages (session 3):**
- [x] Add react-router-dom + NavBar component (top nav with links, ThemeToggle moved from SearchPage)
- [x] Update App.tsx with BrowserRouter (routes: /, /market, /compare, /property/:id)
- [x] Market Overview page (GET /analytics/market-overview backend endpoint + full frontend page with 6 chart sections + summary table)
- [x] Compare Areas page (PostcodeMultiInput chip component + side-by-side multi-postcode charts using existing getAnalytics)
- [x] Property Detail page (GET /properties/{id}/similar backend endpoint + price history chart + appreciation stats + features/floorplans + similar properties)
- [x] PropertyCard "View full details" link to /property/:id
- [x] SPA fallback for production (FastAPI serves index.html for non-API routes)
- [x] New backend schemas (MarketOverview, PriceRangeBucket in schemas.py)
- [x] 4 new API tests (market-overview empty + with data, similar properties not found + with similar)
- [x] TypeScript types + API client functions (MarketOverview, getMarketOverview, getProperty, getSimilarProperties)

**Housing Insights page (session 4):**
_Backend endpoint + schemas + frontend API client already done (uncommitted from session 3)_
- [x] Create HousingInsightsPage.tsx (Plotly charts: histogram, time series, scatter w/ trend line, postcode heatmap; KPI cards; filter panel; investment deals table)
- [x] Add /insights route to App.tsx + NavBar link
- [x] Add backend tests for housing-insights endpoint (3 tests: empty DB, with data, filters)
- [x] Verify: 55 tests pass, tsc clean, 27 routes loaded
- [x] Commit all Housing Insights changes

---

## Session 5 — Feature Backlog (10 tasks)
_Researched 2026-02-10. Each task has full implementation details so it can be picked up cold._

### 1. ~~Interactive Map View with Property Markers~~ DONE
- [x] **Backend**: `GET /api/v1/properties/geo` endpoint with lat/lng. Geocoding via Postcodes.io batch API cached on Property model.
- [x] **Frontend**: `MapViewPage.tsx` with react-leaflet, marker clustering, colour-coded by price, popup with property summary.
- [x] **Route**: `/map` in App.tsx + NavBar link.

### 2. ~~EPC Energy Rating Enrichment~~ DONE
- [x] **Backend**: `app/enrichment/epc.py` service with `fetch_epc_for_postcode()`. `POST /api/v1/enrich/epc/{postcode}` endpoint with fuzzy address matching. EPC columns on Property model (`epc_rating`, `epc_score`, `epc_environment_impact`, `estimated_energy_cost`). DB migration for new columns. Config: `EPC_API_EMAIL` + `EPC_API_KEY`.
- [x] **Frontend**: `EPCBadge.tsx` component (colour-coded A-G). Shown on PropertyCard + PropertyDetailPage header. Full EPC detail section on PropertyDetailPage (score, environment impact, energy cost).
- [x] **Tests**: 3 new tests (no properties 404, no creds returns 0, EPC fields on property response). 66 total.
- **Commit**: TBD

### 3. ~~Crime Data by Postcode~~ DONE
- [x] **Backend**: `CrimeStats` table + `app/enrichment/crime.py` service (Postcodes.io geocoding + Police API, 12-month history, 30-day cache). `GET /api/v1/analytics/postcode/{postcode}/crime` endpoint.
- [x] **Frontend**: `CrimeSection.tsx` component with pie chart (category breakdown), horizontal bar chart (top categories), monthly trend line. Dark mode support. Shown on PropertyDetailPage.
- [x] **Tests**: 3 new tests (endpoint exists, empty result, cached data served). 66 total.
- **Commit**: TBD

### 4. Property Price Modelling Tab — DONE
- [x] **Backend**: `app/modelling/` package (data_assembly, trainer, predictor). LightGBM + XGBoost with temporal/random splits. Feature registry from Property + Sale + CrimeStats + parsed extra_features (60 features incl. sale_year/month/quarter). In-memory model store. Metrics: R², RMSE, MAE, MAPE (no sklearn). 5 endpoints: `GET /model/features`, `POST /model/train`, `GET /model/{id}/predict`, `GET /model/{id}/predict-postcode`.
- [x] **Frontend**: `ModellingPage.tsx` — two-column layout. Sidebar: target (price, price/sqft, price change %), model (LightGBM/XGBoost), split (random slider / temporal date picker), feature selection (grouped by category, select all/none). Results: metrics stat cards, feature importance bar chart (Recharts), predicted vs actual scatter (Plotly), residual histogram (Plotly), worst predictions table, single-property prediction, postcode prediction table (top 50/100/200 with predicted vs last sale + diff %), prediction date picker.
- [x] **Tests**: 12 new tests (features endpoint, validation, LightGBM/XGBoost training, temporal/random splits, prediction). 95 total passing.
- [x] **Fixes**: Dtype coercion for crime/EPC/numeric columns (object→float), SPA catch-all API guard, 7 new DB indexes across all tables.
- **Commits**: `5c31945`→`a2f1616`, `3818340`, `8c9f5da`

### 4b. Transport Distance Enrichment — DONE
- [x] **Backend**: `app/enrichment/transport.py` — NaPTAN CSV download + parquet cache (~96MB→~15MB), static UK airports (25) + ports (20) dicts, haversine math, scipy `cKDTree` for O(log n) nearest-neighbour. 10 new Property columns (6 distances, 3 names, bus count). `POST /api/v1/enrich/transport/{postcode}` endpoint. Auto-geocodes properties without coordinates.
- [x] **Modelling**: 10 transport features in FEATURE_REGISTRY under "Transport" category (7 numeric distances + 3 categorical station/airport names). Integrated into `_build_record()` and `_CATEGORICAL_FEATURES`.
- [x] **Frontend**: `TransportSection.tsx` component with 2x3 distance grid (rail, tube, tram, bus, airport, port), station names, bus stops within 500m count. "Compute Transport Distances" button for enrichment. Added to PropertyDetailPage.
- [x] **Tests**: 14 new tests (haversine, cartesian, static data validation, endpoint, feature registry). 109 total passing.
- [x] **Bug fix**: Scraper duplicate sale IntegrityError — wrapped sale inserts in `db.begin_nested()` savepoint.
- **Commits**: `66fc6fa`, `af0a094`, `98359b9`, `8ffaa2f`

### 5. ~~Flood Risk Assessment~~ DONE
- [x] **Backend**: `app/enrichment/flood.py` — Environment Agency API, `flood_risk_level` column, `GET /api/v1/analytics/postcode/{postcode}/flood-risk`.
- [x] **Frontend**: `FloodRiskSection.tsx` component on PropertyDetailPage.
- [x] **Tests**: Flood risk endpoint tests.

### 6. ~~Capital Growth Tracker & Forecasting~~ DONE
- [x] **Backend**: `GET /api/v1/analytics/postcode/{postcode}/growth` (CAGR, volatility, forecast). `GET /api/v1/analytics/growth-leaderboard` (top postcodes by CAGR).
- [x] **Frontend**: Growth section on PropertyDetailPage, leaderboard on MarketOverviewPage.

### 7. ~~Planning Applications Nearby~~ DONE
- [x] **Backend**: `PlanningApplication` table, `app/enrichment/planning.py`, `GET /api/v1/analytics/postcode/{postcode}/planning`.
- [x] **Frontend**: `PlanningSection.tsx` with status badges on PropertyDetailPage.

### 8. PDF Report Export
- [ ] **Backend**: Install `weasyprint` (HTML-to-PDF) or `reportlab` (programmatic PDF). Create `app/export/pdf_report.py`. Endpoint: `POST /api/v1/export/report` with body `{postcode, include_sections: ["summary","charts","properties","crime","epc"]}`. Generate HTML template using Jinja2 (already a FastAPI dependency). Render charts as static SVGs using matplotlib (add to requirements.txt) — Recharts/Plotly are client-side only. Sections: cover page (postcode, date, property count), summary stats table, price trend chart (matplotlib line), property type breakdown (matplotlib bar), top 10 properties table, growth metrics, and any enrichment data available (crime, EPC, flood risk). Return PDF as `StreamingResponse` with `content-type: application/pdf`.
- [ ] **Frontend**: "Download Report" button on SearchPage analytics dashboard and MarketOverviewPage. Section checkboxes in a dropdown to customise report contents. Loading spinner while PDF generates. Use `window.open()` or `<a download>` to trigger download.
- [ ] **Config**: Add `REPORT_TEMPLATE_DIR` to config (default: `app/export/templates/`).
- [ ] **Tests**: Test PDF generation returns valid PDF bytes, test with empty data returns appropriate message, test section inclusion/exclusion.
- **Why**: Investors and agents need to share analysis with partners, lenders, and clients. A downloadable PDF report adds professional credibility. Strong differentiator for a free tool. Pairs well with all enrichment data (crime, EPC, flood, growth).
- **Complexity**: Medium
- **Deps**: `weasyprint` or `reportlab`, `matplotlib` for server-side charts, `jinja2` (already installed).

### 9. ~~Skip Already-Scraped Postcodes~~ DONE
- [x] **Backend**: `skip_existing` + `force` params on both scrape endpoints, `_is_postcode_fresh()` helper with `SCRAPER_FRESHNESS_DAYS` config (default 7), `postcodes_skipped` in area response, `skipped` in single response.
- [x] **Frontend**: "Re-scrape existing" checkbox in SearchBar, skip message shown in UI.
- [x] **Tests**: 5 new tests (fresh/stale/unknown postcode, schema fields). 60 total passing.
- **Commit**: `e372b25`

---

### 10. ~~Shared Enrichment Infrastructure~~ DONE
- [x] **Backend**: `app/enrichment/ons_postcode.py` (ONS LSOA lookup), `app/enrichment/coord_convert.py` (BNG→WGS84), enrichment schemas in `app/schemas.py`, bulk enrichment orchestrator (`app/enrichment/bulk.py`), 11 enrichment types supported.
- **Commits**: `7c63f51`

### 11. ~~IMD Deprivation Enrichment~~ DONE
- [x] **Backend**: `app/enrichment/imd.py` — 8 decile domains via LSOA bridge, 8 Property columns.
- [x] **Frontend**: `IMDSection.tsx` component with radar chart.
- **Commits**: `ca64a13`

### 12. ~~Broadband Speed Enrichment~~ DONE
- [x] **Backend**: `app/enrichment/broadband.py` — Ofcom Connected Nations, 4 metrics.
- [x] **Frontend**: `BroadbandSection.tsx` component with speed bars.
- **Commits**: `42668d5`

### 13. ~~Schools & Ofsted Enrichment~~ DONE
- [x] **Backend**: `app/enrichment/schools.py` — GIAS CSV, BNG→WGS84, 4 cKDTrees, 10 features.
- [x] **Frontend**: `SchoolsSection.tsx` component with school cards.
- **Commits**: `db76a8c`

### 14. ~~Healthcare Enrichment~~ DONE
- [x] **Backend**: `app/enrichment/healthcare.py` — NHS GP + hospitals, ONS geocoded, 2 cKDTrees, 5 features.
- [x] **Frontend**: `HealthcareSection.tsx` component.
- **Commits**: `23c9f65`

### 15. ~~Supermarket Enrichment~~ DONE
- [x] **Backend**: `app/enrichment/supermarkets.py` — Geolytix, 3 cKDTrees (all/premium/budget), 6 features.
- [x] **Frontend**: `SupermarketsSection.tsx` component.
- **Commits**: `d39a0a6`

### 16. ~~Fix Broken Data Source URLs~~ DONE
- [x] Fixed NaPTAN, GIAS, Geolytix, Ofcom, ONS data URLs and parsing for 5 enrichment sources.
- **Commits**: `f77cd67`

### 17. ~~Model Training: Use All Sales~~ DONE
- [x] Changed model training to use all sales per property (not just latest) for more training data.
- **Commits**: `8075075`

### 18. ~~VPS Deployment Config~~ DONE
- [x] systemd services, deploy script, production .env, accumulated bug fixes.
- **Commits**: `ad612d6`

### 19. ~~Rebrand to UK House Prices~~ DONE
- [x] Renamed from Rightmove to UK House Prices throughout. Fixed flood severity bug.
- **Commits**: `ac9c364`

### 20. ~~Current Listings Scrape Mode~~ DONE
- [x] **Backend**: Added `mode` query param to scrape endpoints (`house_prices` or `for_sale`). Scrapes Rightmove for-sale listings with asking prices, stores with `listing_status="for_sale"`.
- [x] **Frontend**: SearchBar toggle between "House Prices" and "Current Listings" modes. PropertyCard shows asking prices for listings. Separate rendering paths for each mode.
- [x] **Bug fix**: Mode-aware freshness check — for-sale data no longer blocks house-prices scraping.
- [x] **Bug fix**: `listing_only` filter on `/properties` endpoint properly separates listing vs sales data.
- **Commits**: `e7abbb9`, `3d92e9e`, `71379d4`

### 21. ~~Has Listing Filter for Housing Insights~~ DONE
- [x] **Backend**: Added `has_listing` query param to housing-insights endpoint. SQL-level filter on `Property.listing_status`.
- [x] **Frontend**: "Has Current Listing" checkbox in filter panel alongside Garden, Parking, Chain Free.
- [x] **Tests**: 2 new tests (listing_only filter, has_listing filter). 129 total passing.
- **Commits**: `8f1c13e`

### 22. ~~Stop App Button~~ DONE
- [x] **Backend**: `POST /api/v1/admin/shutdown` endpoint with `SIGTERM`.
- [x] **Frontend**: "Stop App" button in NavBar next to Reset DB.
- **Commits**: `531b6ee`

---

## Remaining Backlog
- [ ] PDF Report Export (weasyprint + matplotlib)
- [ ] Stamp Duty & Mortgage Calculators (pure frontend)
- [ ] Rental Yield Calculator (ONS data + calculations)

---

## Verification
- 129 backend tests passing: `pytest tests/ -v`
- Frontend types clean: `npx tsc --noEmit`
- Ruff lint clean: `ruff check app/ tests/`
- App loads: `python -c "from app.main import app"` (51 endpoints)
- 7 new DB indexes on Property, Sale, CrimeStats, PlanningApplication
