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
- [ ] Commit all Housing Insights changes

---

## Verification
- 55 backend tests passing: `pytest tests/ -v`
- Frontend types clean: `npx tsc --noEmit`
- App loads: `python -c "from app.main import app"` (27 routes)
