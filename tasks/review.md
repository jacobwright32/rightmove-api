# Comprehensive Codebase Review — 2026-02-11

Full review across 4 dimensions: backend code quality, frontend code quality, test coverage, and documentation. Issues prioritised P0 (critical) through P3 (low).

---

## P0 — Critical (Fix Immediately)

### 1. Path Traversal in SPA Fallback
**File:** `app/main.py:107-109`
The catch-all route serves files from `frontend/dist` using the raw URL path. An attacker can use `../../etc/passwd` to read arbitrary files.
**Fix:** Validate `os.path.realpath(file_path).startswith(os.path.realpath(_frontend_dist))`.

### 2. SSRF via Weak URL Validation
**File:** `app/routers/scraper.py:393-399`
`"rightmove.co.uk" not in body.url` is trivially bypassed (`http://evil.com/?rightmove.co.uk`).
**Fix:** Use `urllib.parse.urlparse(body.url).hostname.endswith("rightmove.co.uk")`.

### 3. HousingInsightsPage Not Lazy-Loaded (Bundle Size)
**File:** `frontend/src/App.tsx:5-7`
`HousingInsightsPage` eagerly imports the full Plotly library (~1MB). It should be lazy-loaded like `MapViewPage` and `ModellingPage`.
**Fix:** `const HousingInsightsPage = lazy(() => import("./pages/HousingInsightsPage"));`

---

## P1 — High (Fix Soon)

### 4. `_model_store` Unbounded Memory Leak
**File:** `app/modelling/trainer.py:125`
Every `/model/train` call adds to an in-memory dict with no eviction. Repeated training consumes all memory.
**Fix:** Add LRU eviction (max 10 models, evict oldest on insert).

### 5. Thread-Unsafe `_status["log"]` Mutation
**File:** `app/enrichment/bulk.py:55-57`
Background thread appends to `_status["log"]` while the request thread reads it via `get_status()`. No lock protects log mutations.
**Fix:** Use `_lock` around all `_status["log"]` mutations, or use `collections.deque(maxlen=100)`.

### 6. Health Check DB Session Leak
**File:** `app/main.py:70-76`
If `db.execute()` throws, `db.close()` is never called.
**Fix:** Wrap in `try/finally` or use a context manager.

### 7. `list_properties` with `limit=0` Returns All Properties (OOM)
**File:** `app/routers/properties.py:27,44-45`
Default `limit=0` means no limit. Large DBs will OOM.
**Fix:** Default to `limit=100`, add `Query(le=1000)` hard cap.

### 8. `get_housing_insights` Loads All Rows (No LIMIT)
**File:** `app/routers/analytics.py:283`
When no filters applied, loads entire Sale x Property join. OOM risk.
**Fix:** Add a hard limit (e.g., 50,000 rows) or paginate.

### 9. No Error Boundary in React
**File:** `frontend/src/App.tsx`
Any render-time error crashes the entire app with a white screen.
**Fix:** Add a React error boundary component wrapping `<Routes>`.

### 10. NavBar Not Responsive
**File:** `frontend/src/components/NavBar.tsx:14-45`
7 links overflow on mobile. No hamburger menu or wrapping.
**Fix:** Add a responsive hamburger menu or `flex-wrap` with overflow handling.

### 11. Missing 404 Route
**File:** `frontend/src/App.tsx:20-29`
Navigating to `/nonexistent` shows a blank page.
**Fix:** Add `<Route path="*" element={<NotFoundPage />} />`.

### 12. `<a href>` Used Instead of `<Link>` for Internal Navigation
**Files:** `MarketOverviewPage.tsx:293`, `ModellingPage.tsx:801,924`
`<a href="/property/...">` causes full page reloads instead of SPA navigation.
**Fix:** Replace with `<Link to="/property/...">`.

### 13. Two Plotly Import Strategies → Double Bundle
`HousingInsightsPage` uses `plotly.js-dist-min` + factory pattern; `ModellingPage` uses `react-plotly.js` directly. May produce two separate Plotly bundles.
**Fix:** Standardise on one import pattern.

### 14. No Debounce on MapViewPage Filter
**File:** `frontend/src/pages/MapViewPage.tsx:68-85`
Every keystroke fires an API request. No cancellation of previous requests.
**Fix:** Add 300ms debounce with `useDebouncedValue` hook.

### 15. AbortController Not Wired to HTTP Requests
**File:** `frontend/src/hooks/usePostcodeSearch.ts:46-51`
AbortController is created but signal is never passed to axios. HTTP requests continue server-side.
**Fix:** Pass `{ signal: controller.signal }` to axios config in API client functions.

---

## P2 — Medium (Address in Next Sprint)

### Backend

#### 16. SQL Wildcards Not Escaped in LIKE Filters
**Files:** `properties.py:35,66,252,319`, `analytics.py:586`
User input containing `%` or `_` produces unexpected matches.
**Fix:** Escape `%` and `_` before interpolation.

#### 17. User Hyperparameters Injected Without Validation
**File:** `app/modelling/trainer.py:179-180`
User-provided dict merged directly into LightGBM/XGBoost params.
**Fix:** Whitelist allowed hyperparameter keys.

#### 18. `predict_postcode` N+1 Queries (300+)
**File:** `app/modelling/predictor.py:99-123`
One query per property for latest sale, plus `_get_crime_by_postcode` called per-property.
**Fix:** Batch-fetch latest sales with a subquery; call crime query once.

#### 19. Growth Leaderboard Runs 500 Join Queries
**File:** `app/routers/analytics.py:1133-1134`
`_compute_annual_medians` called per-postcode in a loop.
**Fix:** Batch-fetch all sales, compute in-memory, or use SQL aggregation.

#### 20. 12 Sequential HTTP Calls in Crime Data
**File:** `app/enrichment/crime.py:97-103`
Sequential calls to Police API per month.
**Fix:** Use `ThreadPoolExecutor` for concurrent requests (3-4 at a time).

#### 21. `get_market_overview` Loads All Prices into Python
**File:** `app/routers/analytics.py:60-65,108-116`
Fetches all sale prices and type rows into memory.
**Fix:** Use SQL `AVG()`, `GROUP BY`, `COUNT()` aggregations.

#### 22. Inconsistent `datetime.utcnow()` vs `datetime.now(tz)`
**Files:** `planning.py:191`, `listing.py:188`
**Fix:** Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` everywhere.

#### 23. Error Messages Expose Internal Details
**File:** `app/routers/modelling.py:78,104`
Exception messages forwarded to client.
**Fix:** Log full exception, return generic message.

#### 24. No Rate Limiting on Enrichment Endpoints
Scraper endpoints have rate limits but enrichment endpoints (calling external APIs) don't.
**Fix:** Add `@limiter.limit()` to enrichment endpoints.

#### 25. `bulk_start` No Validation on `delay`
**File:** `app/routers/enrichment.py:297-310`
User can set `delay=0` to hammer APIs.
**Fix:** `Query(default=3.0, ge=0.5, le=60)`.

#### 26. `PostcodePredictionResponse.predictions` is Untyped `list`
**File:** `app/schemas.py:488`
**Fix:** Change to `list[PostcodePredictionItem]` (Python 3.9: `List[PostcodePredictionItem]`).

#### 27. Dead Code `if False` in `get_coverage`
**File:** `app/enrichment/bulk.py:370-372`
**Fix:** Remove the dead branch.

### Frontend

#### 28. `any` in Catch Blocks (ModellingPage)
**File:** `ModellingPage.tsx:154,169,184`
**Fix:** Use `unknown` with `import { isAxiosError } from "axios"` type narrowing.

#### 29. CompareAreasPage Data Transformations Not Memoized
**File:** `CompareAreasPage.tsx:65-73`
4 expensive transforms run on every render.
**Fix:** Wrap in `useMemo(() => ..., [results])`.

#### 30. `usePlotlyTheme` Duplicated
**Files:** `HousingInsightsPage.tsx:65-72`, `ModellingPage.tsx:27-33`
**Fix:** Extract to `hooks/usePlotlyTheme.ts`.

#### 31. `PLOTLY_CONFIG` Duplicated
**Files:** `HousingInsightsPage.tsx:74`, `ModellingPage.tsx:25`
**Fix:** Extract to shared constant.

#### 32. `parseJsonArray` Duplicated
**Files:** `PropertyCard.tsx:12-19`, `PropertyDetailPage.tsx:27-34`
**Fix:** Extract to `utils/parsing.ts`.

#### 33. Tooltip Style Object Duplicated in 5+ Files
**Fix:** Extract to `chartTheme.ts` as `getTooltipStyle()`.

#### 34. Missing Keyboard Navigation for Suggestion Dropdowns
**Files:** `SearchBar.tsx:103-121`, `PostcodeMultiInput.tsx:111-124`
No arrow-key navigation or ARIA listbox roles.

#### 35. Empty Prices Crash in Heatmaps
**Files:** `PostcodeHeatmap.tsx:13-15`, `PriceHeatmap.tsx:13-15`
`Math.min(...[])` returns `Infinity` when all prices are null/0.
**Fix:** Guard: `if (prices.length === 0) return ...`

#### 36. `ExportResponse` Defined in client.ts Instead of types.ts
**File:** `frontend/src/api/client.ts:129-134`
**Fix:** Move to `types.ts` for consistency.

#### 37. No Axios Request Timeout
**File:** `frontend/src/api/client.ts:30`
**Fix:** Add `timeout: 30000` to axios create config.

---

## P3 — Low (Nice to Have)

### Backend
- 38. `_is_postcode_fresh` loads all Property objects instead of using aggregate query (`scraper.py:82-99`)
- 39. `_backfill_parsed_fields` loads all rows into memory (`database.py:71-87`) — use chunked processing
- 40. `get_postcode_status` loads all properties instead of aggregate (`properties.py:252-256`)
- 41. `suggest_postcodes` side-scrapes Rightmove on a GET request (`properties.py:280-287`) — surprising side effect
- 42. NaPTAN download blocks request thread (`transport.py:138-161`)
- 43. SQLite WAL mode not enabled — concurrent writes from bulk thread can cause `database is locked`
- 44. CORS allows `methods=["*"]` and `headers=["*"]` — tighten to actual methods/headers used
- 45. `skip_existing=false` and `force=true` are equivalent — confusing API surface
- 46. `PropertyList` renders all items without virtualization (`PropertyList.tsx`)
- 47. `ModellingPage` is 977 lines — extract sub-components to separate files
- 48. `HousingInsightsPage` is 901 lines — same
- 49. Inconsistent chart heights across components (250/280/300/350/400px)
- 50. No global axios error interceptor — each caller handles errors differently

---

## Documentation Issues

### Critical
- 51. `.env.example` has stale defaults: `SCRAPER_DELAY=0.5` (should be 0.25), `RATE_LIMIT_SCRAPE=5/min` (should be 30/min)
- 52. README TrainRequest example uses wrong field names (`split_type`/`test_size` vs `split_strategy`/`split_params`)

### High
- 53. README missing 4 bulk enrichment endpoints, EnrichmentPage, correct route `/model` (not `/modelling`)
- 54. README says 34 endpoints (actual ~40) and 7 pages (actual 8)
- 55. `.env.example` missing `LISTING_FRESHNESS_HOURS` and `NAPTAN_MAX_AGE_DAYS`
- 56. `tasks/todo.md` tasks 5, 6, 7 (flood, growth, planning) are done but unchecked
- 57. CLAUDE.md duplicated in two locations with formatting issues

### Medium
- 58. `AreaScrapeResponse` in `types.ts` missing `postcodes_failed` field
- 59. No `Field(description=...)` on any Pydantic model — poor OpenAPI docs
- 60. README architecture diagram says "7 pages" (should be 8)

---

## Test Coverage Gaps

### HIGH Priority (write these first)
- 61. `POST /scrape/postcode` happy path — mock scraper, verify upsert logic
- 62. `_upsert_property()` unit tests — insert, update, sale dedup, IntegrityError handling
- 63. `GET /model/{id}/predict-postcode` — entirely untested endpoint
- 64. `predict_postcode()` service function — zero coverage
- 65. `assemble_dataset()` for `price_per_sqft` and `price_change_pct` targets — zero coverage
- 66. `train_model()` with `log_transform=True` — untested training option
- 67. Mock all external HTTP calls — 6 tests hit real APIs (Postcodes.io, Police, EA, EPC, Planning)
- 68. Fix conditional assertion in `test_flood_risk_cached_on_property` — test always passes

### MEDIUM Priority
- 69. `GET /properties/postcode/{postcode}/status` — untested
- 70. `GET /analytics/postcode/{pc}/price-trends` — untested
- 71. `GET /analytics/postcode/{pc}/summary` — untested
- 72. `geocode_postcode()` and `batch_geocode_postcodes()` — shared dependency, no tests
- 73. `_assess_risk_from_areas()` in flood.py — complex zone parsing, untested
- 74. `predict_single()` with XGBoost model — only tested with LightGBM
- 75. Housing insights filter tests (tenure, bathrooms, price range, EPC, garden)
- 76. Add factory fixtures (`make_property(**overrides)`) to reduce test boilerplate

### LOW Priority
- 77. `GET /health` endpoint
- 78. Bulk enrichment endpoints (coverage, status, start, stop)
- 79. `_parse_application_type()`, `_parse_listing_date()` unit tests
- 80. Postcode analytics: bedroom-distribution, sales-volume, postcode-comparison

---

## Recommended Fix Order

### Phase 1: Security (1-2 hours)
Fix items 1, 2 (path traversal, SSRF). These are exploitable vulnerabilities.

### Phase 2: Stability (2-3 hours)
Fix items 4-8 (memory leak, thread safety, session leak, OOM guards).
Fix item 22 (datetime consistency).
Fix item 27 (dead code).

### Phase 3: Frontend Critical (2-3 hours)
Fix items 3, 9-15 (lazy load, error boundary, responsive nav, 404 route, Link vs a, debounce).

### Phase 4: Test Infrastructure (3-4 hours)
Fix items 67-68 (mock external APIs, fix false-positive test).
Write items 61-66 (high-priority missing tests).
Add factory fixtures (item 76).

### Phase 5: Performance (2-3 hours)
Fix items 18-21 (N+1 queries, batch operations, SQL aggregation).
Fix items 28-33 (memoization, deduplication).

### Phase 6: Documentation (1 hour)
Fix items 51-60 (stale docs, missing endpoints, todo.md updates).

### Phase 7: Polish (2-3 hours)
Fix remaining P3 items based on priority.
