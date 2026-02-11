# Lessons Learned

## Session 6: 2026-02-11 (modelling tab + bug fixes)
- **Zombie processes on Windows**: A stale uvicorn process can hold a port indefinitely and resist `taskkill`/`Stop-Process`. Don't waste time fighting it — switch to a different port and update vite.config.ts proxy accordingly.
- **SPA catch-all intercepts API routes**: The `/{full_path:path}` catch-all in FastAPI serves `index.html` for unknown routes. If API router registration fails silently (import error, stale cache), API requests get HTML instead of JSON. Always add an API guard: `if full_path.startswith("api/"): return 404 JSON`.
- **uvicorn --reload may not reload on Windows**: File watchers (WatchFiles) can be unreliable on Windows. After code changes, verify with a direct curl test. If stale, restart uvicorn manually.
- **LightGBM/XGBoost reject object dtype columns**: When a pandas column has mixed `float` + `None` values (e.g. crime data for postcodes without data), pandas infers `object` dtype. Must explicitly coerce with `pd.to_numeric(errors="coerce")`. Single-row DataFrames are especially prone to this — use unconditional `pd.to_numeric().astype(float)` for all non-categorical columns, not just `dtype == object` checks.
- **Feature importance division by zero**: When all feature importances sum to 0, normalizing produces NaN which breaks JSON serialization. Guard with `if total > 0 else 0.0`.
- **DB indexes matter for modelling**: Crime aggregation queries (`GROUP BY postcode, category`) and sale lookups (`property_id + price_numeric`) need composite indexes. Add indexes proactively when adding new query-heavy features.

## Session 4: 2026-02-10 (housing insights)
- **Commit as you go**: Don't batch all changes into one big commit at the end. Commit after each logical unit of work (e.g., backend endpoint done → commit, frontend page done → commit, tests done → commit).
- **Update tasks at every step**: Mark tasks `in_progress` before starting, `completed` immediately after finishing. Update `tasks/todo.md` checkboxes in lockstep. Never let task state drift from actual progress.
- **Plotly.js-dist-min needs a .d.ts**: The minified Plotly bundle has no TypeScript declarations. Create `src/plotly.d.ts` with `declare module "plotly.js-dist-min"` to avoid TS7016.
- **Use `createPlotlyComponent` factory**: When using `plotly.js-dist-min` (not full `plotly.js`), import via factory: `createPlotlyComponent(Plotly)` from `react-plotly.js/factory`.

## Session 3: 2026-02-10 (new pages)
- **SPA fallback for FastAPI**: When using react-router-dom BrowserRouter, FastAPI's `StaticFiles(html=True)` doesn't handle SPA routing for paths like `/market`. Need a catch-all `/{full_path:path}` route that serves `index.html` for non-file paths.
- **TypeScript strict mode and Record<string, unknown>**: Typed interfaces can't be directly cast to `Record<string, unknown>[]` — use a helper function with `any` instead of inline casts.
- **Parallel subagent for backend**: Launching a backend-focused subagent while building frontend in parallel saved significant time.

## Session 2: 2026-02-10 (continued)
- **Update tests when changing routes**: Adding API versioning prefix (`/api/v1/`) broke 7 tests that used old URLs. Always update tests alongside route changes.
- **Check dark mode on all components**: PostcodeHeatmap was missed when adding dark: classes. When doing theme work, use `grep` to verify every `bg-white` has a corresponding `dark:bg-*`.
- **Recharts needs explicit dark mode**: Recharts doesn't inherit CSS dark mode — grids, axes, tooltips all need explicit color props. Created `useDarkMode` hook + `getChartColors` utility for reuse.
- **CSS content-visibility > JS virtualization**: For simple long lists, `content-visibility: auto` gives ~10x render improvement with zero JS deps (per react-best-practices skill).
- **useSyncExternalStore for DOM state**: Best way to make React reactive to DOM changes (like class list) without useEffect polling.

## Session 1: 2026-02-10
- **Always save context**: User lost session context after computer restart. Memory files + task tracking now set up to persist across sessions.
