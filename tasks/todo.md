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

---

## Verification
- 48 backend tests passing: `pytest tests/ -v`
- Frontend types clean: `npx tsc --noEmit`
- App loads: `python -c "from app.main import app"`
