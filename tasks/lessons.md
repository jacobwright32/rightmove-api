# Lessons Learned

## Session 2: 2026-02-10 (continued)
- **Update tests when changing routes**: Adding API versioning prefix (`/api/v1/`) broke 7 tests that used old URLs. Always update tests alongside route changes.
- **Check dark mode on all components**: PostcodeHeatmap was missed when adding dark: classes. When doing theme work, use `grep` to verify every `bg-white` has a corresponding `dark:bg-*`.
- **Recharts needs explicit dark mode**: Recharts doesn't inherit CSS dark mode — grids, axes, tooltips all need explicit color props. Created `useDarkMode` hook + `getChartColors` utility for reuse.
- **CSS content-visibility > JS virtualization**: For simple long lists, `content-visibility: auto` gives ~10x render improvement with zero JS deps (per react-best-practices skill).
- **useSyncExternalStore for DOM state**: Best way to make React reactive to DOM changes (like class list) without useEffect polling.

## Session 1: 2026-02-10
- **Always save context**: User lost session context after computer restart. Memory files + task tracking now set up to persist across sessions.
