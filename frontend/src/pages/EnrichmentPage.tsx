import { useCallback, useEffect, useRef, useState } from "react";
import {
  getBulkCoverage,
  getBulkStatus,
  startBulkEnrichment,
  stopBulkEnrichment,
} from "../api/client";
import type { BulkEnrichmentStatus, CoverageResponse } from "../api/types";

const ENRICHMENT_TYPES = [
  { id: "geocode", label: "Geocoding" },
  { id: "transport", label: "Transport" },
  { id: "epc", label: "EPC" },
  { id: "crime", label: "Crime" },
  { id: "flood", label: "Flood Risk" },
  { id: "planning", label: "Planning" },
  { id: "imd", label: "IMD Deprivation" },
  { id: "broadband", label: "Broadband" },
  { id: "schools", label: "Schools" },
];

export default function EnrichmentPage() {
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [status, setStatus] = useState<BulkEnrichmentStatus | null>(null);
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(
    new Set(ENRICHMENT_TYPES.map((t) => t.id))
  );
  const [delay, setDelay] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchCoverage = useCallback(async () => {
    try {
      setCoverage(await getBulkCoverage());
    } catch {
      /* ignore */
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await getBulkStatus();
      setStatus(s);
      return s;
    } catch {
      return null;
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchCoverage();
    fetchStatus();
  }, [fetchCoverage, fetchStatus]);

  // Poll while running
  useEffect(() => {
    if (status?.running) {
      pollRef.current = setInterval(async () => {
        const s = await fetchStatus();
        // Refresh coverage every 30s while running
        if (s && s.postcodes_done % 10 === 0) {
          fetchCoverage();
        }
      }, 3000);
    } else if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
      // Refresh coverage when stopped
      fetchCoverage();
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [status?.running, fetchStatus, fetchCoverage]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [status?.log]);

  const handleStart = async () => {
    setError(null);
    try {
      const types = Array.from(selectedTypes);
      const s = await startBulkEnrichment(types, delay);
      if (s.error) {
        setError(s.error);
      } else {
        setStatus(s);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start");
    }
  };

  const handleStop = async () => {
    try {
      setStatus(await stopBulkEnrichment());
    } catch {
      /* ignore */
    }
  };

  const toggleType = (id: string) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () =>
    setSelectedTypes(new Set(ENRICHMENT_TYPES.map((t) => t.id)));
  const selectNone = () => setSelectedTypes(new Set());

  const pct = (filled: number, total: number) =>
    total > 0 ? ((filled / total) * 100).toFixed(1) : "0.0";

  const progressPct =
    status && status.postcodes_total > 0
      ? ((status.postcodes_done / status.postcodes_total) * 100).toFixed(1)
      : "0";

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
        Data Enrichment
      </h1>

      {/* Coverage Table */}
      {coverage && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h2 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Feature Coverage
          </h2>
          <p className="mb-3 text-sm text-gray-500 dark:text-gray-400">
            {coverage.total_properties.toLocaleString()} properties across{" "}
            {coverage.total_postcodes.toLocaleString()} postcodes
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b dark:border-gray-600">
                  <th className="py-2 pr-4 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Feature
                  </th>
                  <th className="px-4 py-2 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Coverage
                  </th>
                  <th className="px-4 py-2 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Progress
                  </th>
                  <th className="py-2 pl-4 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Notes
                  </th>
                </tr>
              </thead>
              <tbody>
                {coverage.features.map((f) => {
                  const p = parseFloat(pct(f.filled, f.total));
                  const barColor =
                    p >= 90
                      ? "bg-green-500"
                      : p >= 50
                        ? "bg-yellow-500"
                        : p >= 10
                          ? "bg-orange-500"
                          : "bg-red-500";
                  return (
                    <tr
                      key={f.name}
                      className="border-b last:border-0 dark:border-gray-700"
                    >
                      <td className="py-2 pr-4 font-medium text-gray-800 dark:text-gray-200">
                        {f.name}
                      </td>
                      <td className="px-4 py-2 text-gray-600 dark:text-gray-400">
                        {f.filled.toLocaleString()} / {f.total.toLocaleString()}{" "}
                        ({pct(f.filled, f.total)}%)
                      </td>
                      <td className="px-4 py-2">
                        <div className="h-2 w-32 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-600">
                          <div
                            className={`h-full rounded-full ${barColor}`}
                            style={{ width: `${Math.min(p, 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2 pl-4 text-xs text-gray-500 dark:text-gray-400">
                        {f.note}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Enrichment Controls */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left: Config */}
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h2 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Bulk Enrichment
          </h2>

          {/* Type selection */}
          <div className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Enrichment Types
              </label>
              <div className="flex gap-2 text-xs">
                <button
                  onClick={selectAll}
                  className="text-blue-600 hover:underline dark:text-blue-400"
                >
                  All
                </button>
                <button
                  onClick={selectNone}
                  className="text-blue-600 hover:underline dark:text-blue-400"
                >
                  None
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {ENRICHMENT_TYPES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => toggleType(t.id)}
                  disabled={status?.running}
                  className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                    selectedTypes.has(t.id)
                      ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-400 dark:bg-blue-900/30 dark:text-blue-300"
                      : "border-gray-300 text-gray-500 dark:border-gray-600 dark:text-gray-400"
                  } disabled:opacity-50`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Delay */}
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Delay between API calls: {delay}s
            </label>
            <input
              type="range"
              min={1}
              max={10}
              step={0.5}
              value={delay}
              onChange={(e) => setDelay(parseFloat(e.target.value))}
              disabled={status?.running}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-400">
              <span>1s (faster)</span>
              <span>10s (safer)</span>
            </div>
          </div>

          {/* Start / Stop */}
          <div className="flex gap-3">
            {!status?.running ? (
              <button
                onClick={handleStart}
                disabled={selectedTypes.size === 0}
                className="rounded-md bg-green-600 px-6 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 dark:bg-green-500 dark:hover:bg-green-600"
              >
                Start Enrichment
              </button>
            ) : (
              <button
                onClick={handleStop}
                className="rounded-md bg-red-600 px-6 py-2 text-sm font-medium text-white hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600"
              >
                Stop
              </button>
            )}
            <button
              onClick={fetchCoverage}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-700"
            >
              Refresh Stats
            </button>
          </div>

          {error && (
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}

          {/* Progress */}
          {status?.running && (
            <div className="mt-4">
              <div className="mb-1 flex justify-between text-sm text-gray-600 dark:text-gray-400">
                <span>
                  {status.postcodes_done} / {status.postcodes_total} postcodes
                </span>
                <span>{progressPct}%</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-600">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <div className="mt-2 flex gap-4 text-xs text-gray-500 dark:text-gray-400">
                <span>
                  Current: {status.current_postcode} ({status.current_type})
                </span>
                <span>
                  Properties: {status.properties_enriched.toLocaleString()}
                </span>
                <span>Errors: {status.errors}</span>
              </div>
            </div>
          )}

          {status && !status.running && status.finished_at && (
            <div className="mt-4 rounded-md bg-green-50 p-3 text-sm text-green-800 dark:bg-green-900/30 dark:text-green-300">
              Completed {status.postcodes_done} / {status.postcodes_total}{" "}
              postcodes ({status.properties_enriched.toLocaleString()}{" "}
              properties, {status.errors} errors)
            </div>
          )}
        </div>

        {/* Right: Log */}
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h2 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Log
          </h2>
          <div
            ref={logRef}
            className="h-80 overflow-y-auto rounded-md bg-gray-900 p-3 font-mono text-xs text-green-400"
          >
            {status?.log && status.log.length > 0 ? (
              status.log.map((line, i) => <div key={i}>{line}</div>)
            ) : (
              <div className="text-gray-500">
                No enrichment running. Click "Start Enrichment" to begin.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
