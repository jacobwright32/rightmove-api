import { useCallback, useEffect, useState } from "react";
import { getOutcodeSummaries, scrapeArea } from "../api/client";
import type { OutcodeSummary } from "../api/types";

export default function ScrapedPostcodesPage() {
  const [outcodes, setOutcodes] = useState<OutcodeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showMode, setShowMode] = useState<"all" | "done" | "pending">("all");

  // Scrape options (same as SearchBar)
  const [mode, setMode] = useState<"house_prices" | "for_sale">("house_prices");
  const [pages, setPages] = useState(1);
  const [linkCount, setLinkCount] = useState(0);
  const [floorplan, setFloorplan] = useState(false);
  const [extraFeatures, setExtraFeatures] = useState(false);
  const [saveParquet, setSaveParquet] = useState(false);
  const [force, setForce] = useState(false);

  // Per-outcode scraping state
  const [scraping, setScraping] = useState<Record<string, boolean>>({});
  const [scrapeResults, setScrapeResults] = useState<Record<string, string>>({});

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOutcodes(await getOutcodeSummaries());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load outcodes");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleScrape = async (outcode: string) => {
    setScraping((s) => ({ ...s, [outcode]: true }));
    setScrapeResults((r) => ({ ...r, [outcode]: "" }));
    try {
      const apiLinkCount = linkCount === 0 ? undefined : linkCount === -1 ? 0 : linkCount;
      const result = await scrapeArea(outcode, {
        pages,
        linkCount: apiLinkCount,
        maxPostcodes: 0,
        floorplan,
        extraFeatures,
        saveParquet,
        force,
        mode,
      });
      setScrapeResults((r) => ({
        ...r,
        [outcode]: `${result.postcodes_scraped.length} scraped, ${result.postcodes_skipped.length} skipped, ${result.total_properties} properties`,
      }));
      // Refresh data after scrape
      fetchData();
    } catch (e: unknown) {
      setScrapeResults((r) => ({
        ...r,
        [outcode]: e instanceof Error ? e.message : "Scrape failed",
      }));
    } finally {
      setScraping((s) => ({ ...s, [outcode]: false }));
    }
  };

  const isDone = (o: OutcodeSummary) =>
    o.total_postcodes > 0 && o.scraped_postcodes >= o.total_postcodes;

  const isPartial = (o: OutcodeSummary) =>
    o.scraped_postcodes > 0 && o.total_postcodes > 0 && o.scraped_postcodes < o.total_postcodes;

  const filtered = outcodes.filter((o) => {
    const matchesFilter = o.outcode.toLowerCase().includes(filter.toLowerCase().replace(/\s/g, ""));
    if (!matchesFilter) return false;
    if (showMode === "done") return isDone(o);
    if (showMode === "pending") return !isDone(o) && o.total_postcodes > 0;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    const aDone = isDone(a) ? 0 : isPartial(a) ? 1 : 2;
    const bDone = isDone(b) ? 0 : isPartial(b) ? 1 : 2;
    if (aDone !== bDone) return aDone - bDone;
    return a.outcode.localeCompare(b.outcode);
  });

  const doneCount = outcodes.filter(isDone).length;
  const partialCount = outcodes.filter(isPartial).length;
  const totalProperties = outcodes.reduce((s, o) => s + o.property_count, 0);
  const totalSales = outcodes.reduce((s, o) => s + o.sale_count, 0);
  const anyScraping = Object.values(scraping).some(Boolean);

  const formatDate = (iso: string | null) => {
    if (!iso) return "-";
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  };

  const pct = (o: OutcodeSummary) =>
    o.total_postcodes > 0
      ? Math.round((o.scraped_postcodes / o.total_postcodes) * 100)
      : 0;

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
        Scraped Outcodes
      </h1>

      <div className="flex gap-6">
        {/* ── Sidebar ── */}
        <aside className="w-56 shrink-0">
          <div className="sticky top-20 space-y-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Scrape Options</h2>

            {/* Mode toggle */}
            <div>
              <label className="mb-1 block text-xs text-gray-500 dark:text-gray-400">Mode</label>
              <div className="flex overflow-hidden rounded-md border border-gray-300 dark:border-gray-600">
                <button
                  type="button"
                  onClick={() => setMode("house_prices")}
                  className={`flex-1 px-2 py-1.5 text-xs font-medium transition-colors ${
                    mode === "house_prices"
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-600 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                  }`}
                >
                  House Prices
                </button>
                <button
                  type="button"
                  onClick={() => setMode("for_sale")}
                  className={`flex-1 px-2 py-1.5 text-xs font-medium transition-colors ${
                    mode === "for_sale"
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-600 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                  }`}
                >
                  Listings
                </button>
              </div>
            </div>

            {/* Pages */}
            <div>
              <label className="mb-1 block text-xs text-gray-500 dark:text-gray-400">Pages</label>
              <input
                type="number"
                min={1}
                max={50}
                value={pages}
                onChange={(e) => setPages(Math.max(1, Number(e.target.value)))}
                className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              />
            </div>

            {/* Detail links */}
            {mode === "house_prices" && (
              <div>
                <label className="mb-1 block text-xs text-gray-500 dark:text-gray-400">Detail links</label>
                <select
                  value={linkCount}
                  onChange={(e) => setLinkCount(Number(e.target.value))}
                  className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                >
                  <option value={0}>Off (fast)</option>
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={-1}>All</option>
                </select>
              </div>
            )}

            {/* Checkboxes */}
            <div className="space-y-2">
              {mode === "house_prices" && (
                <>
                  <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                    <input
                      type="checkbox"
                      checked={floorplan}
                      onChange={(e) => setFloorplan(e.target.checked)}
                      className="rounded border-gray-300 dark:border-gray-600"
                    />
                    Floorplans
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                    <input
                      type="checkbox"
                      checked={extraFeatures}
                      onChange={(e) => setExtraFeatures(e.target.checked)}
                      className="rounded border-gray-300 dark:border-gray-600"
                    />
                    Key features
                  </label>
                </>
              )}
              <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                <input
                  type="checkbox"
                  checked={saveParquet}
                  onChange={(e) => setSaveParquet(e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
                Save as you go
              </label>
              <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                <input
                  type="checkbox"
                  checked={force}
                  onChange={(e) => setForce(e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
                Re-scrape existing
              </label>
            </div>

            <hr className="border-gray-200 dark:border-gray-700" />

            {/* Summary stats */}
            <div className="space-y-1 text-xs text-gray-500 dark:text-gray-400">
              <p><span className="font-medium text-green-600 dark:text-green-400">{doneCount}</span> done</p>
              <p><span className="font-medium text-amber-600 dark:text-amber-400">{partialCount}</span> partial</p>
              <p>{totalProperties.toLocaleString()} properties</p>
              <p>{totalSales.toLocaleString()} sales</p>
            </div>

            <button
              onClick={fetchData}
              disabled={loading}
              className="w-full rounded-md bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>
        </aside>

        {/* ── Main content ── */}
        <div className="min-w-0 flex-1">
          {/* Filter + controls */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <input
              type="text"
              placeholder="Filter outcodes..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-48 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
            <div className="flex overflow-hidden rounded-md border border-gray-300 dark:border-gray-600">
              {(["all", "done", "pending"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setShowMode(m)}
                  className={`px-3 py-2 text-xs font-medium capitalize transition-colors ${
                    showMode === m
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-600 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
            <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">
              {sorted.length} outcodes
            </span>
          </div>

          {error && (
            <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
              {error}
            </div>
          )}

          {/* Outcode grid */}
          {loading ? (
            <div className="py-12 text-center text-gray-500">Loading...</div>
          ) : sorted.length === 0 ? (
            <div className="py-12 text-center text-gray-500">
              {outcodes.length === 0 ? "No outcode data found" : "No outcodes match filter"}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {sorted.map((o) => {
                const done = isDone(o);
                const partial = isPartial(o);
                const isExp = expanded === o.outcode;
                const isScraping = scraping[o.outcode];
                const result = scrapeResults[o.outcode];

                return (
                  <div
                    key={o.outcode}
                    className={`relative rounded-lg border-2 p-3 transition-all ${
                      done
                        ? "border-green-400 bg-green-50 dark:border-green-600 dark:bg-green-900/20"
                        : partial
                          ? "border-amber-400 bg-amber-50 dark:border-amber-600 dark:bg-amber-900/20"
                          : "border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800"
                    } ${isExp ? "col-span-2 row-span-2" : ""}`}
                  >
                    {/* Header — clickable to expand */}
                    <div
                      className="cursor-pointer"
                      onClick={() => setExpanded(isExp ? null : o.outcode)}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`text-lg font-bold ${
                          done
                            ? "text-green-700 dark:text-green-400"
                            : partial
                              ? "text-amber-700 dark:text-amber-400"
                              : "text-gray-500 dark:text-gray-500"
                        }`}>
                          {o.outcode}
                        </span>
                        {done && (
                          <span className="text-green-600 dark:text-green-400" title="Complete">
                            &#10003;
                          </span>
                        )}
                      </div>

                      {/* Progress bar */}
                      {o.total_postcodes > 0 && (
                        <div className="mt-2">
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                            <div
                              className={`h-full rounded-full transition-all ${
                                done ? "bg-green-500" : partial ? "bg-amber-500" : "bg-gray-300"
                              }`}
                              style={{ width: `${pct(o)}%` }}
                            />
                          </div>
                          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            {o.scraped_postcodes}/{o.total_postcodes} postcodes
                          </p>
                        </div>
                      )}

                      {!isExp && o.scraped_postcodes > 0 && (
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {o.property_count} props
                        </p>
                      )}
                    </div>

                    {/* Expanded detail */}
                    {isExp && (
                      <div className="mt-3 space-y-2 border-t border-gray-200 pt-3 dark:border-gray-600">
                        <div className="space-y-1 text-sm">
                          <p className="text-gray-700 dark:text-gray-300">
                            <span className="text-gray-500 dark:text-gray-400">Properties:</span>{" "}
                            {o.property_count.toLocaleString()}
                          </p>
                          <p className="text-gray-700 dark:text-gray-300">
                            <span className="text-gray-500 dark:text-gray-400">Sales:</span>{" "}
                            {o.sale_count.toLocaleString()}
                          </p>
                          <p className="text-gray-700 dark:text-gray-300">
                            <span className="text-gray-500 dark:text-gray-400">Coverage:</span>{" "}
                            {pct(o)}% ({o.scraped_postcodes}/{o.total_postcodes})
                          </p>
                          <p className="text-gray-700 dark:text-gray-300">
                            <span className="text-gray-500 dark:text-gray-400">Updated:</span>{" "}
                            {formatDate(o.last_updated)}
                          </p>
                        </div>

                        {/* Scrape result message */}
                        {result && (
                          <p className="text-xs text-blue-600 dark:text-blue-400">{result}</p>
                        )}
                      </div>
                    )}

                    {/* Scrape button — always visible */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleScrape(o.outcode);
                      }}
                      disabled={isScraping || anyScraping}
                      className={`mt-2 w-full rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                        isScraping
                          ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                          : "bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:hover:bg-blue-900/40"
                      } disabled:opacity-50`}
                    >
                      {isScraping ? "Scraping..." : "Scrape"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
