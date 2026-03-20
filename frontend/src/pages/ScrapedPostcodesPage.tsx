import { useCallback, useEffect, useState } from "react";
import { getOutcodeSummaries } from "../api/client";
import type { OutcodeSummary } from "../api/types";

export default function ScrapedPostcodesPage() {
  const [outcodes, setOutcodes] = useState<OutcodeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showMode, setShowMode] = useState<"all" | "done" | "pending">("all");

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

  const isDone = (o: OutcodeSummary) =>
    o.total_postcodes > 0 && o.scraped_postcodes >= o.total_postcodes;

  const isPartial = (o: OutcodeSummary) =>
    o.scraped_postcodes > 0 && o.total_postcodes > 0 && o.scraped_postcodes < o.total_postcodes;

  // Filter
  const filtered = outcodes.filter((o) => {
    const matchesFilter = o.outcode.toLowerCase().includes(filter.toLowerCase().replace(/\s/g, ""));
    if (!matchesFilter) return false;
    if (showMode === "done") return isDone(o);
    if (showMode === "pending") return !isDone(o) && o.total_postcodes > 0;
    return true;
  });

  // Sort: done first, then partial, then unsscraped; within each group alphabetical
  const sorted = [...filtered].sort((a, b) => {
    const aDone = isDone(a) ? 0 : isPartial(a) ? 1 : 2;
    const bDone = isDone(b) ? 0 : isPartial(b) ? 1 : 2;
    if (aDone !== bDone) return aDone - bDone;
    return a.outcode.localeCompare(b.outcode);
  });

  // Stats
  const doneCount = outcodes.filter(isDone).length;
  const partialCount = outcodes.filter(isPartial).length;
  const totalProperties = outcodes.reduce((s, o) => s + o.property_count, 0);
  const totalSales = outcodes.reduce((s, o) => s + o.sale_count, 0);
  const scrapedOutcodes = outcodes.filter((o) => o.scraped_postcodes > 0).length;

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
    <main className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
        Scraped Outcodes
      </h1>

      {/* Summary cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-5">
        {[
          { label: "Total Outcodes", value: outcodes.length },
          { label: "Done", value: doneCount, color: "text-green-600 dark:text-green-400" },
          { label: "Partial", value: partialCount, color: "text-amber-600 dark:text-amber-400" },
          { label: "Properties", value: totalProperties.toLocaleString() },
          { label: "Sales", value: totalSales.toLocaleString() },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
          >
            <p className="text-sm text-gray-500 dark:text-gray-400">{s.label}</p>
            <p className={`text-2xl font-bold ${s.color ?? "text-gray-900 dark:text-gray-100"}`}>
              {loading ? "-" : s.value}
            </p>
          </div>
        ))}
      </div>

      {/* Filter + controls */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Filter outcodes..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-48 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
        />
        <div className="flex rounded-md border border-gray-300 dark:border-gray-600">
          {(["all", "done", "pending"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setShowMode(mode)}
              className={`px-3 py-2 text-xs font-medium capitalize transition-colors first:rounded-l-md last:rounded-r-md ${
                showMode === mode
                  ? "bg-blue-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
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
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6">
          {sorted.map((o) => {
            const done = isDone(o);
            const partial = isPartial(o);
            const isExpanded = expanded === o.outcode;

            return (
              <div
                key={o.outcode}
                onClick={() => setExpanded(isExpanded ? null : o.outcode)}
                className={`relative cursor-pointer rounded-lg border-2 p-3 transition-all hover:shadow-md ${
                  done
                    ? "border-green-400 bg-green-50 dark:border-green-600 dark:bg-green-900/20"
                    : partial
                      ? "border-amber-400 bg-amber-50 dark:border-amber-600 dark:bg-amber-900/20"
                      : "border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800"
                } ${isExpanded ? "col-span-2 row-span-2" : ""}`}
              >
                {/* Outcode label */}
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

                {/* Compact stats */}
                {!isExpanded && o.scraped_postcodes > 0 && (
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {o.property_count} props
                  </p>
                )}

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="mt-3 space-y-1 border-t border-gray-200 pt-3 text-sm dark:border-gray-600">
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
                )}
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
