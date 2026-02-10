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

### 2. EPC Energy Rating Enrichment
- [ ] **Backend**: Register at https://epc.opendatacommunities.org/ (free, instant API key). Create `app/enrichment/epc.py` service. Endpoint: `GET https://epc.opendatacommunities.org/api/v1/domestic/search?postcode=SW20+8ND` with `Authorization: Basic {base64(email:apikey)}` header. Returns JSON array with: `current-energy-rating` (A-G), `current-energy-efficiency` (1-100), `environment-impact-current`, `heating-cost-current`, `hot-water-cost-current`, `lighting-cost-current`, `mainheat-description`, `walls-description`, `roof-description`. Add columns to Property model: `epc_rating` (String, 1 char), `epc_score` (Integer), `epc_environment_impact` (Integer), `estimated_energy_cost` (Integer, annual £). Create enrichment endpoint: `POST /api/v1/enrich/epc/{postcode}` that batch-fetches and updates all properties in that postcode.
- [ ] **Frontend**: EPC badge component (colour-coded A=green to G=red) on PropertyCard and PropertyDetailPage. EPC distribution bar chart on analytics pages. Filter by EPC rating on HousingInsightsPage (already has `epc_rating` filter param but no data).
- [ ] **Config**: Add `EPC_API_EMAIL` and `EPC_API_KEY` to `.env.example` and `app/config.py`.
- [ ] **Tests**: Test EPC enrichment with mocked API response, test badge renders correctly for each rating.
- **Why**: EPC ratings increasingly affect property values and rental eligibility (minimum EPC E for UK rentals). Most-requested data dimension for property buyers. The filter already exists on HousingInsightsPage but has no backing data.
- **Complexity**: Small-Medium
- **Deps**: None new (httpx already installed). Needs free API key registration.

### 3. Crime Data by Postcode
- [ ] **Backend**: UK Police API is free, no auth required. Create `app/enrichment/crime.py`. Step 1: Convert postcode to lat/lng via Postcodes.io (`GET https://api.postcodes.io/postcodes/{postcode}`). Step 2: Fetch crimes (`GET https://data.police.uk/api/crimes-street/all-crime?lat={lat}&lng={lng}&date={YYYY-MM}`). Returns array with `category` (e.g. "burglary", "anti-social-behaviour", "violent-crime"), `month`, `location`. Create `CrimeStats` table: `id`, `postcode`, `month` (YYYY-MM), `category`, `count`, `fetched_at`. Endpoint: `GET /api/v1/analytics/postcode/{postcode}/crime` returns crime breakdown + 12-month trend. Cache results for 30 days (check `fetched_at`).
- [ ] **Frontend**: Crime summary section on PropertyDetailPage — pie chart of crime categories (Recharts PieChart), 12-month trend line. Crime comparison column on CompareAreasPage. "Safety score" badge (based on total crimes per 1000 population vs national average). Use dark mode chart theme from existing `chartTheme.ts`.
- [ ] **Tests**: Test crime endpoint with mocked police API response, test empty/missing data handling, test cache expiry logic.
- **Why**: Crime is top-3 factor in property purchase decisions. Free API, no auth, easy integration. Adds massive value for buyers evaluating neighbourhoods.
- **Complexity**: Small
- **Deps**: None new. Free API, no registration needed.

### 4. Stamp Duty & Mortgage Calculators
- [ ] **Frontend only — no backend needed**. Create `StampDutyCalculator.tsx` component. UK SDLT bands (2024-25, check for updates): 0% up to £250k, 5% £250k-£925k, 10% £925k-£1.5M, 12% over £1.5M. First-time buyer relief: 0% up to £425k, 5% £425k-£625k (no relief if over £625k). Additional property surcharge: +3% on all bands. Non-UK resident surcharge: +2%. Inputs: price (pre-filled from property), buyer type radio (standard/first-time/additional/non-resident). Output: total stamp duty, effective rate %, breakdown table by band.
- [ ] **Mortgage calculator**: `MortgageCalculator.tsx`. Formula: `M = P * [r(1+r)^n] / [(1+r)^n - 1]` where P=principal, r=monthly rate, n=total months. Inputs: property price (pre-filled), deposit % (slider 5-50%, default 10%), interest rate % (default 4.5%), term years (default 25). Output: monthly payment, total interest, total cost, stress test at +2% rate. Show amortization summary.
- [ ] **Integration**: Place both on PropertyDetailPage (accordion/tabs below price history). Also add as standalone `/calculators` page in nav for general use without a specific property.
- [ ] **Tests**: Unit test stamp duty calculation for edge cases (exactly on band boundaries, first-time relief cutoff at £625k, additional property surcharge stacking).
- **Why**: Every property portal has these. Expected functionality. Pure frontend, no API costs, quick to build. Directly connects price data to what buyers actually care about: "can I afford this?"
- **Complexity**: Small

### 5. Rental Yield Calculator
- [ ] **Backend**: Create `app/enrichment/rental.py`. Source average rents from ONS Private Rental Market Statistics (free CSV download from ons.gov.uk, updates quarterly) by postcode district and bedroom count. Alternative: scrape Rightmove rental listings for the same postcode (reuse existing scraper with rental URL pattern: `rightmove.co.uk/house-prices/{postcode}.html` → change to `/properties-to-let/`). Create `RentalEstimate` table: `postcode_district` (e.g. "SW20"), `bedrooms`, `avg_monthly_rent`, `median_monthly_rent`, `sample_size`, `source`, `updated_at`. Endpoint: `GET /api/v1/analytics/postcode/{postcode}/rental-yield` returns gross yield, net yield, monthly rent estimate. Gross yield = (annual_rent / purchase_price) × 100. Net yield subtracts: management 10%, maintenance 1% of value, void periods 4 weeks/year, insurance ~£300/yr, landlord license where applicable.
- [ ] **Frontend**: Yield calculator widget on PropertyDetailPage — shows gross/net yield with breakdown. Yield heatmap on MarketOverviewPage (colour postcodes by average yield). Add yield column to investment deals table on HousingInsightsPage. Yield comparison on CompareAreasPage.
- [ ] **Tests**: Test yield calculations, test with missing rental data returns appropriate fallback.
- **Why**: Single most important metric for buy-to-let investors. Transforms the app from price viewer into investment analysis tool. Your HousingInsights page already identifies "investment deals" — adding yield data makes that 10x more useful.
- **Complexity**: Medium

### 6. Flood Risk Assessment
- [ ] **Backend**: Environment Agency API is free, no auth. Create `app/enrichment/flood.py`. Two data sources: (1) EA Flood Risk API: `GET https://environment.data.gov.uk/flood-monitoring/id/floods?lat={lat}&lng={lng}&dist=1` for current warnings. (2) Open Flood Risk by Postcode: download CSV from https://www.getthedata.com/open-flood-risk-by-postcode (maps every UK postcode to flood risk zone 1/2/3). Add `flood_risk_level` column to Property model (values: "very_low", "low", "medium", "high"). Endpoint: `GET /api/v1/analytics/postcode/{postcode}/flood-risk` returns risk level + any active flood warnings.
- [ ] **Frontend**: Flood risk badge on PropertyCard (green/amber/red). Flood risk section on PropertyDetailPage with explanation text. Flood risk comparison on CompareAreasPage. Filter by flood risk on HousingInsightsPage.
- [ ] **Tests**: Test risk classification logic, test with/without active warnings.
- **Why**: Directly impacts property values, insurance costs, and mortgage approvals. Many buyers don't check until late in the process — surfacing it early saves time and money. Free data, simple integration.
- **Complexity**: Small

### 7. Capital Growth Tracker & Forecasting
- [ ] **Backend**: Extend existing analytics in `app/routers/analytics.py`. New endpoint: `GET /api/v1/analytics/postcode/{postcode}/growth` with `?periods=1,3,5,10` param. For each period: calculate CAGR (Compound Annual Growth Rate) = `(end_price/start_price)^(1/years) - 1`. Use median prices per year to smooth outliers. Also calculate: volatility (standard deviation of annual returns), max drawdown (largest peak-to-trough decline), Sharpe-like ratio (growth / volatility). For forecasting: use scipy `curve_fit` with linear and polynomial (degree 2) models on historical median prices. Return predicted price at +1yr, +3yr, +5yr with confidence bands (±1 std dev of residuals). New endpoint: `GET /api/v1/analytics/growth-leaderboard?limit=20` returns top postcodes by 5yr CAGR.
- [ ] **Frontend**: Growth dashboard section on PropertyDetailPage (CAGR badges for 1/3/5/10yr). Growth forecast chart with confidence bands (Recharts AreaChart with gradient fill for confidence). Growth leaderboard table on MarketOverviewPage (sortable by period). Growth comparison overlay on CompareAreasPage.
- [ ] **Tests**: Test CAGR calculation, test with insufficient data (< 2 years), test forecast confidence band width.
- **Why**: Builds on existing data with no new external sources. Growth metrics are what investors use to evaluate areas. Forecasting (even simple) adds perceived sophistication. The leaderboard creates a "discovery" use case — which areas are growing fastest?
- **Complexity**: Small-Medium

### 8. Planning Applications Nearby
- [ ] **Backend**: Use Planning Data platform API: `GET https://www.planning.data.gov.uk/api/v1/entity.json?dataset=planning-application&geometry_reference={postcode_lat_lng}&limit=50`. Also available as bulk CSV download. Create `PlanningApplication` table: `reference`, `description`, `status` (submitted/approved/refused), `decision_date`, `application_type` (householder/full/outline/listed-building), `latitude`, `longitude`, `local_authority`, `fetched_at`. Create `app/enrichment/planning.py`. Endpoint: `GET /api/v1/analytics/postcode/{postcode}/planning` returns recent applications within ~500m radius. Flag major developments (10+ dwellings, commercial, infrastructure) separately.
- [ ] **Frontend**: Planning applications section on PropertyDetailPage — list with status badges (green=approved, amber=pending, red=refused). Map overlay showing application locations (integrate with map view from task 1). "Major developments" alert badge on PropertyCard if significant applications nearby. Filter: show only major/all applications.
- [ ] **Tests**: Test planning endpoint with mocked response, test radius filtering, test major development flagging logic.
- **Why**: Nearby developments significantly affect property values (positively: regeneration; negatively: overlooking, traffic). Investors need this to avoid nasty surprises. Data is free via gov.uk open data.
- **Complexity**: Medium

### 9. PDF Report Export
- [ ] **Backend**: Install `weasyprint` (HTML-to-PDF) or `reportlab` (programmatic PDF). Create `app/export/pdf_report.py`. Endpoint: `POST /api/v1/export/report` with body `{postcode, include_sections: ["summary","charts","properties","crime","epc"]}`. Generate HTML template using Jinja2 (already a FastAPI dependency). Render charts as static SVGs using matplotlib (add to requirements.txt) — Recharts/Plotly are client-side only. Sections: cover page (postcode, date, property count), summary stats table, price trend chart (matplotlib line), property type breakdown (matplotlib bar), top 10 properties table, growth metrics, and any enrichment data available (crime, EPC, flood risk). Return PDF as `StreamingResponse` with `content-type: application/pdf`.
- [ ] **Frontend**: "Download Report" button on SearchPage analytics dashboard and MarketOverviewPage. Section checkboxes in a dropdown to customise report contents. Loading spinner while PDF generates. Use `window.open()` or `<a download>` to trigger download.
- [ ] **Config**: Add `REPORT_TEMPLATE_DIR` to config (default: `app/export/templates/`).
- [ ] **Tests**: Test PDF generation returns valid PDF bytes, test with empty data returns appropriate message, test section inclusion/exclusion.
- **Why**: Investors and agents need to share analysis with partners, lenders, and clients. A downloadable PDF report adds professional credibility. Strong differentiator for a free tool. Pairs well with all enrichment data (crime, EPC, flood, growth).
- **Complexity**: Medium
- **Deps**: `weasyprint` or `reportlab`, `matplotlib` for server-side charts, `jinja2` (already installed).

### 10. Skip Already-Scraped Postcodes
- [ ] **Backend**: Add `skip_existing` query param (default: `true`) to `POST /scrape/postcode/{postcode}` and `POST /scrape/area/{partial}`. When true: check `GET /properties/postcode/{postcode}/status` — if `has_data` is true AND `last_updated` is within a configurable freshness window (default 7 days, add `SCRAPER_FRESHNESS_DAYS` to config.py), skip the scrape and return a response like `{"message": "Postcode SW20 8ND already scraped (42 properties, last updated 2026-02-08)", "skipped": true, "properties_scraped": 0}`. For area scraping: filter the postcode list before the loop, log which were skipped. Add `force` query param to override skip behaviour.
- [ ] **Frontend**: Show skip feedback in UI — "Already have data for X postcodes, scraping Y new ones". Option checkbox: "Re-scrape existing postcodes" (maps to `skip_existing=false`). Progress indicator showing "Skipped 3, Scraping 5 of 8 postcodes".
- [ ] **Tests**: Test skip logic with fresh data (should skip), test with stale data (should re-scrape), test `force=true` overrides skip, test area scrape correctly filters postcode list.
- **Why**: Currently every scrape request hits Rightmove even if data exists. This wastes rate limit quota, slows down area scrapes, and risks getting blocked. With 30/min rate limit, skipping existing data means you can cover more ground faster.
- **Complexity**: Small

---

## Verification
- 55 backend tests passing: `pytest tests/ -v`
- Frontend types clean: `npx tsc --noEmit`
- App loads: `python -c "from app.main import app"` (27 routes)
