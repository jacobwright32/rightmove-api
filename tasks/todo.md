# Rightmove API - Task Tracker

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

### 1. Interactive Map View with Property Markers
- [ ] **Backend**: Add `GET /api/v1/properties/geo` endpoint — returns properties with lat/lng coordinates. Use Postcodes.io batch API (`POST https://api.postcodes.io/postcodes` with array of postcodes) to geocode. Cache lat/lng on the Property model (add `latitude` and `longitude` nullable Float columns via Alembic migration). Batch geocode on first request, store results so subsequent loads are instant.
- [ ] **Frontend**: New `MapViewPage.tsx` using `react-leaflet` (free, OpenStreetMap tiles, no API key). Install: `npm install leaflet react-leaflet @types/leaflet`. Use `react-leaflet-cluster` for marker clustering at low zoom. Colour-code markers by price range (green = below median, red = above). Click marker → popup with PropertyCard summary + link to `/property/:id`. Toggle between list/map view on SearchPage. Import leaflet CSS in main.tsx: `import 'leaflet/dist/leaflet.css'`.
- [ ] **Route**: Add `/map` route in App.tsx + NavBar link.
- [ ] **Tests**: Test geo endpoint returns lat/lng, test with missing coordinates gracefully handled.
- **Why**: Maps are the #1 way users browse properties on Rightmove/Zoopla. Spatial patterns (expensive streets, clusters) become immediately visible. 60%+ of property searchers prefer map-based browsing.
- **Complexity**: Medium
- **Deps**: `react-leaflet`, `leaflet`, `@types/leaflet`, `react-leaflet-cluster`. Backend: `httpx` for Postcodes.io calls (already installed).

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
- [x] **Backend**: `app/modelling/` package (data_assembly, trainer, predictor). LightGBM + XGBoost with temporal/random splits. Feature registry from Property + Sale + CrimeStats + parsed extra_features (50+ features). In-memory model store. Metrics: R², RMSE, MAE, MAPE (no sklearn). 3 endpoints: `GET /model/features`, `POST /model/train`, `GET /model/{id}/predict`.
- [x] **Frontend**: `ModellingPage.tsx` — two-column layout. Sidebar: target (price, price/sqft, price change %), model (LightGBM/XGBoost), split (random slider / temporal date picker), feature selection (grouped by category, select all/none). Results: metrics stat cards, feature importance bar chart (Recharts), predicted vs actual scatter (Plotly), residual histogram (Plotly), worst predictions table, single-property prediction input.
- [x] **Tests**: 12 new tests (features endpoint, validation, LightGBM/XGBoost training, temporal/random splits, prediction). 95 total passing.
- **Commits**: `5c31945`, `e83e98c`, `b992dd6`, `fb623c4`, `706be09`, `a2f1616`, `4c3a580`

### 5. Flood Risk Assessment
- [ ] **Backend**: Environment Agency API is free, no auth. Create `app/enrichment/flood.py`. Two data sources: (1) EA Flood Risk API: `GET https://environment.data.gov.uk/flood-monitoring/id/floods?lat={lat}&lng={lng}&dist=1` for current warnings. (2) Open Flood Risk by Postcode: download CSV from https://www.getthedata.com/open-flood-risk-by-postcode (maps every UK postcode to flood risk zone 1/2/3). Add `flood_risk_level` column to Property model (values: "very_low", "low", "medium", "high"). Endpoint: `GET /api/v1/analytics/postcode/{postcode}/flood-risk` returns risk level + any active flood warnings.
- [ ] **Frontend**: Flood risk badge on PropertyCard (green/amber/red). Flood risk section on PropertyDetailPage with explanation text. Flood risk comparison on CompareAreasPage. Filter by flood risk on HousingInsightsPage.
- [ ] **Tests**: Test risk classification logic, test with/without active warnings.
- **Why**: Directly impacts property values, insurance costs, and mortgage approvals. Many buyers don't check until late in the process — surfacing it early saves time and money. Free data, simple integration.
- **Complexity**: Small

### 6. Capital Growth Tracker & Forecasting
- [ ] **Backend**: Extend existing analytics in `app/routers/analytics.py`. New endpoint: `GET /api/v1/analytics/postcode/{postcode}/growth` with `?periods=1,3,5,10` param. For each period: calculate CAGR (Compound Annual Growth Rate) = `(end_price/start_price)^(1/years) - 1`. Use median prices per year to smooth outliers. Also calculate: volatility (standard deviation of annual returns), max drawdown (largest peak-to-trough decline), Sharpe-like ratio (growth / volatility). For forecasting: use scipy `curve_fit` with linear and polynomial (degree 2) models on historical median prices. Return predicted price at +1yr, +3yr, +5yr with confidence bands (±1 std dev of residuals). New endpoint: `GET /api/v1/analytics/growth-leaderboard?limit=20` returns top postcodes by 5yr CAGR.
- [ ] **Frontend**: Growth dashboard section on PropertyDetailPage (CAGR badges for 1/3/5/10yr). Growth forecast chart with confidence bands (Recharts AreaChart with gradient fill for confidence). Growth leaderboard table on MarketOverviewPage (sortable by period). Growth comparison overlay on CompareAreasPage.
- [ ] **Tests**: Test CAGR calculation, test with insufficient data (< 2 years), test forecast confidence band width.
- **Why**: Builds on existing data with no new external sources. Growth metrics are what investors use to evaluate areas. Forecasting (even simple) adds perceived sophistication. The leaderboard creates a "discovery" use case — which areas are growing fastest?
- **Complexity**: Small-Medium

### 7. Planning Applications Nearby
- [ ] **Backend**: Use Planning Data platform API: `GET https://www.planning.data.gov.uk/api/v1/entity.json?dataset=planning-application&geometry_reference={postcode_lat_lng}&limit=50`. Also available as bulk CSV download. Create `PlanningApplication` table: `reference`, `description`, `status` (submitted/approved/refused), `decision_date`, `application_type` (householder/full/outline/listed-building), `latitude`, `longitude`, `local_authority`, `fetched_at`. Create `app/enrichment/planning.py`. Endpoint: `GET /api/v1/analytics/postcode/{postcode}/planning` returns recent applications within ~500m radius. Flag major developments (10+ dwellings, commercial, infrastructure) separately.
- [ ] **Frontend**: Planning applications section on PropertyDetailPage — list with status badges (green=approved, amber=pending, red=refused). Map overlay showing application locations (integrate with map view from task 1). "Major developments" alert badge on PropertyCard if significant applications nearby. Filter: show only major/all applications.
- [ ] **Tests**: Test planning endpoint with mocked response, test radius filtering, test major development flagging logic.
- **Why**: Nearby developments significantly affect property values (positively: regeneration; negatively: overlooking, traffic). Investors need this to avoid nasty surprises. Data is free via gov.uk open data.
- **Complexity**: Medium

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

## Verification
- 95 backend tests passing: `pytest tests/ -v`
- Frontend types clean: `npx tsc --noEmit`
- Ruff lint clean: `ruff check app/ tests/`
- App loads: `python -c "from app.main import app"` (32 routes)
