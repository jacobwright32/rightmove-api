import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getAnalytics } from "../api/client";
import type { PostcodeAnalytics } from "../api/types";
import PostcodeMultiInput from "../components/PostcodeMultiInput";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";
import { formatPrice, formatPriceFull } from "../utils/formatting";

const COLORS = ["#2563eb", "#dc2626", "#16a34a", "#f59e0b"];

export default function CompareAreasPage() {
  const [postcodes, setPostcodes] = useState<string[]>([]);
  const [results, setResults] = useState<Map<string, PostcodeAnalytics>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  async function handleCompare() {
    if (postcodes.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const fetches = postcodes.map((pc) =>
        getAnalytics(pc).then((data) => [pc, data] as const)
      );
      const settled = await Promise.allSettled(fetches);
      const map = new Map<string, PostcodeAnalytics>();
      const failed: string[] = [];
      for (let i = 0; i < settled.length; i++) {
        const result = settled[i];
        if (result.status === "fulfilled") {
          map.set(result.value[0], result.value[1]);
        } else {
          failed.push(postcodes[i]);
        }
      }
      if (map.size === 0) {
        setError("No data found for any of the postcodes. Try scraping them first.");
      } else {
        if (failed.length > 0) {
          setError(`No data for: ${failed.join(", ")}. Showing ${map.size} of ${postcodes.length}.`);
        }
        setResults(map);
      }
    } catch {
      setError("Failed to fetch analytics data.");
    } finally {
      setLoading(false);
    }
  }

  // Build combined price trend data
  const activePostcodes = Array.from(results.keys());
  const priceTrendData = buildMergedTimeSeries(results, "price_trends", "month", "avg_price");
  const volumeData = buildMergedTimeSeries(results, "sales_volume", "year", "count");

  // Build grouped bar data for property types
  const propTypeData = buildGroupedData(results, "property_types", "property_type", "count");

  // Build grouped bar data for bedrooms
  const bedroomData = buildGroupedData(results, "bedroom_distribution", "bedrooms", "count");

  const tooltipStyle = {
    backgroundColor: colors.tooltipBg,
    borderColor: colors.tooltipBorder,
    color: colors.text,
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
        Compare Areas
      </h1>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <PostcodeMultiInput
            postcodes={postcodes}
            onChange={setPostcodes}
            max={4}
            disabled={loading}
          />
        </div>
        <button
          onClick={handleCompare}
          disabled={loading || postcodes.length < 2}
          className="shrink-0 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Loading..." : "Compare"}
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-center text-sm text-yellow-700 dark:border-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
          {error}
        </div>
      )}

      {results.size > 0 && (
        <div className="flex flex-col gap-6">
          {/* Summary table */}
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
              Summary Comparison
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm dark:text-gray-300">
                <thead>
                  <tr className="border-b text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
                    <th scope="col" className="py-2 pr-4">Postcode</th>
                    <th scope="col" className="py-2 pr-4 text-right">Properties</th>
                    <th scope="col" className="py-2 pr-4 text-right">Total Sales</th>
                    <th scope="col" className="py-2 pr-4 text-right">Property Types</th>
                    <th scope="col" className="py-2 text-right">Streets</th>
                  </tr>
                </thead>
                <tbody>
                  {activePostcodes.map((pc, i) => {
                    const analytics = results.get(pc)!;
                    const totalSales = analytics.sales_volume.reduce((s, v) => s + v.count, 0);
                    return (
                      <tr key={pc} className="border-b border-gray-100 dark:border-gray-700">
                        <td className="py-2 pr-4 font-medium">
                          <span
                            className="mr-2 inline-block h-3 w-3 rounded-full"
                            style={{ backgroundColor: COLORS[i] }}
                          />
                          {pc}
                        </td>
                        <td className="py-2 pr-4 text-right">{analytics.property_types.reduce((s, t) => s + t.count, 0)}</td>
                        <td className="py-2 pr-4 text-right">{totalSales}</td>
                        <td className="py-2 pr-4 text-right">{analytics.property_types.length}</td>
                        <td className="py-2 text-right">{analytics.street_comparison.length}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Overlaid price trend chart */}
          {priceTrendData.length > 0 && (
            <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
              <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
                Average Price Trends
              </h3>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={priceTrendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                  <XAxis dataKey="key" tick={{ fontSize: 12, fill: colors.axis }} stroke={colors.grid} />
                  <YAxis tickFormatter={(v: number) => formatPrice(v)} width={70} tick={{ fill: colors.axis }} stroke={colors.grid} />
                  <Tooltip
                    formatter={(v: number) => formatPriceFull(v)}
                    contentStyle={tooltipStyle}
                  />
                  <Legend wrapperStyle={{ color: colors.text }} />
                  {activePostcodes.map((pc, i) => (
                    <Line
                      key={pc}
                      type="monotone"
                      dataKey={pc}
                      name={pc}
                      stroke={COLORS[i]}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Property types grouped bar */}
            {propTypeData.length > 0 && (
              <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
                <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
                  Property Types
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={propTypeData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                    <XAxis dataKey="key" tick={{ fontSize: 11, fill: colors.axis }} stroke={colors.grid} />
                    <YAxis tick={{ fill: colors.axis }} stroke={colors.grid} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend wrapperStyle={{ color: colors.text }} />
                    {activePostcodes.map((pc, i) => (
                      <Bar key={pc} dataKey={pc} name={pc} fill={COLORS[i]} radius={[2, 2, 0, 0]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Bedroom distribution grouped bar */}
            {bedroomData.length > 0 && (
              <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
                <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
                  Bedroom Distribution
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={bedroomData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                    <XAxis dataKey="key" tick={{ fill: colors.axis }} stroke={colors.grid} />
                    <YAxis tick={{ fill: colors.axis }} stroke={colors.grid} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend wrapperStyle={{ color: colors.text }} />
                    {activePostcodes.map((pc, i) => (
                      <Bar key={pc} dataKey={pc} name={pc} fill={COLORS[i]} radius={[2, 2, 0, 0]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Sales volume comparison */}
          {volumeData.length > 0 && (
            <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
              <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
                Sales Volume by Year
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={volumeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                  <XAxis dataKey="key" tick={{ fill: colors.axis }} stroke={colors.grid} />
                  <YAxis tick={{ fill: colors.axis }} stroke={colors.grid} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ color: colors.text }} />
                  {activePostcodes.map((pc, i) => (
                    <Bar key={pc} dataKey={pc} name={pc} fill={COLORS[i]} radius={[2, 2, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {results.size === 0 && !loading && !error && (
        <div className="mt-12 text-center text-gray-400 dark:text-gray-500">
          <p className="text-lg">Add at least 2 postcodes to compare</p>
          <p className="mt-1 text-sm">Postcodes must have been scraped first</p>
        </div>
      )}
    </div>
  );
}

/**
 * Merge time-series data from multiple postcodes into rows keyed by a shared field.
 * E.g., for price_trends: each row has { key: "2023-01", "SW20 8NE": 450000, "E1 6AA": 300000 }
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function extractItems(analytics: PostcodeAnalytics, field: string): any[] {
  return (analytics as any)[field];
}

function buildMergedTimeSeries(
  results: Map<string, PostcodeAnalytics>,
  field: "price_trends" | "sales_volume",
  keyField: string,
  valueField: string
): Record<string, unknown>[] {
  const allKeys = new Set<string>();
  const byPostcode = new Map<string, Map<string, number>>();

  for (const [pc, analytics] of results) {
    const items = extractItems(analytics, field);
    const map = new Map<string, number>();
    for (const item of items) {
      const k = String(item[keyField]);
      allKeys.add(k);
      map.set(k, item[valueField] as number);
    }
    byPostcode.set(pc, map);
  }

  const sorted = Array.from(allKeys).sort();
  return sorted.map((key) => {
    const row: Record<string, unknown> = { key };
    for (const [pc, map] of byPostcode) {
      row[pc] = map.get(key) ?? null;
    }
    return row;
  });
}

/**
 * Build grouped bar chart data from categorical analytics fields.
 */
function buildGroupedData(
  results: Map<string, PostcodeAnalytics>,
  field: "property_types" | "bedroom_distribution",
  keyField: string,
  valueField: string
): Record<string, unknown>[] {
  const allKeys = new Set<string>();
  const byPostcode = new Map<string, Map<string, number>>();

  for (const [pc, analytics] of results) {
    const items = extractItems(analytics, field);
    const map = new Map<string, number>();
    for (const item of items) {
      const k = String(item[keyField]);
      allKeys.add(k);
      map.set(k, item[valueField] as number);
    }
    byPostcode.set(pc, map);
  }

  return Array.from(allKeys)
    .sort()
    .map((key) => {
      const row: Record<string, unknown> = { key };
      for (const [pc, map] of byPostcode) {
        row[pc] = map.get(key) ?? 0;
      }
      return row;
    });
}
