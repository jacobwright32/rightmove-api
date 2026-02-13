import { useCallback, useEffect, useMemo, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import { Link } from "react-router-dom";
import { getHousingInsights } from "../api/client";
import type {
  HousingInsightsFilters,
  HousingInsightsResponse,
  InvestmentDeal,
} from "../api/types";
import StatCard from "../components/StatCard";
import { useDarkMode } from "../hooks/useDarkMode";
import { formatPrice, formatPriceFull } from "../utils/formatting";

const Plot = createPlotlyComponent(Plotly);

const PROPERTY_TYPES = [
  { value: "", label: "All Types" },
  { value: "DETACHED", label: "Detached" },
  { value: "SEMI-DETACHED", label: "Semi-Detached" },
  { value: "TERRACED", label: "Terraced" },
  { value: "FLAT", label: "Flat" },
  { value: "END OF TERRACE", label: "End of Terrace" },
];

const TENURE_OPTIONS = [
  { value: "", label: "Any Tenure" },
  { value: "FREEHOLD", label: "Freehold" },
  { value: "LEASEHOLD", label: "Leasehold" },
];

const EPC_RATINGS = ["", "A", "B", "C", "D", "E", "F", "G"];

const SCATTER_COLORS = [
  "#2563eb",
  "#dc2626",
  "#16a34a",
  "#f59e0b",
  "#8b5cf6",
  "#ec4899",
];

type SortKey = keyof InvestmentDeal;

function linearRegression(xs: number[], ys: number[]) {
  const n = xs.length;
  if (n < 2) return null;
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumX2 = 0;
  for (let i = 0; i < n; i++) {
    sumX += xs[i];
    sumY += ys[i];
    sumXY += xs[i] * ys[i];
    sumX2 += xs[i] * xs[i];
  }
  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) return null;
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

function usePlotlyTheme(dark: boolean) {
  return useMemo(() => {
    const text = dark ? "#d1d5db" : "#374151";
    const grid = dark ? "#374151" : "#e5e7eb";
    const bg = dark ? "#1f2937" : "#ffffff";
    return { text, grid, bg };
  }, [dark]);
}

const PLOTLY_CONFIG = {
  responsive: true,
  displaylogo: false,
};

const inputClass =
  "mt-1 block w-full rounded border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200";

const labelClass = "text-xs font-medium text-gray-600 dark:text-gray-400";

export default function HousingInsightsPage() {
  const [data, setData] = useState<HousingInsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<HousingInsightsFilters>({});
  const [pending, setPending] = useState<HousingInsightsFilters>({});
  const [sortKey, setSortKey] = useState<SortKey>("value_score");
  const [sortAsc, setSortAsc] = useState(false);
  const dark = useDarkMode();
  const theme = usePlotlyTheme(dark);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getHousingInsights(filters)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  const applyFilters = useCallback(() => {
    setFilters({ ...pending });
  }, [pending]);

  const clearFilters = useCallback(() => {
    setPending({});
    setFilters({});
  }, []);

  const handlePostcodeClick = useCallback((postcode: string) => {
    const prefix = postcode.split(" ")[0] || postcode;
    setPending((p) => ({ ...p, postcode_prefix: prefix }));
    setFilters((f) => ({ ...f, postcode_prefix: prefix }));
  }, []);

  const sortedDeals = useMemo(() => {
    if (!data?.investment_deals) return [];
    return [...data.investment_deals].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp =
        typeof av === "number"
          ? av - (bv as number)
          : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });
  }, [data?.investment_deals, sortKey, sortAsc]);

  const handleSort = useCallback((key: SortKey) => {
    setSortKey((prev) => {
      if (prev === key) setSortAsc((a) => !a);
      else setSortAsc(false);
      return key;
    });
  }, []);

  const trendLine = useMemo(() => {
    if (!data?.scatter_data?.length) return null;
    const xs = data.scatter_data.map((d) => d.bedrooms);
    const ys = data.scatter_data.map((d) => d.price);
    const reg = linearRegression(xs, ys);
    if (!reg) return null;
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    return {
      x: [minX, maxX],
      y: [reg.slope * minX + reg.intercept, reg.slope * maxX + reg.intercept],
    };
  }, [data?.scatter_data]);

  const activeFilterCount = Object.values(filters).filter(
    (v) => v !== undefined && v !== "" && v !== null
  ).length;

  // --- Loading ---
  if (loading && !data) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 text-center">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
        <p className="mt-3 text-gray-500 dark:text-gray-400">
          Loading housing insights...
        </p>
      </div>
    );
  }

  // --- Error ---
  if (error && !data) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-400">
          {error}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { kpis } = data;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Housing Insights
        </h1>
        <button
          onClick={() => setFiltersOpen((o) => !o)}
          className="flex items-center gap-2 rounded-lg border bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
        >
          Filters
          {activeFilterCount > 0 && (
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-xs text-white">
              {activeFilterCount}
            </span>
          )}
          <span
            className={`transition-transform ${filtersOpen ? "rotate-180" : ""}`}
          >
            &#x25BE;
          </span>
        </button>
      </div>

      {/* Filter Panel */}
      {filtersOpen && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            <label className="block">
              <span className={labelClass}>Postcode Prefix</span>
              <input
                type="text"
                placeholder="e.g. SW20"
                value={pending.postcode_prefix || ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    postcode_prefix: e.target.value,
                  }))
                }
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Property Type</span>
              <select
                value={pending.property_type || ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    property_type: e.target.value || undefined,
                  }))
                }
                className={inputClass}
              >
                {PROPERTY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className={labelClass}>Min Bedrooms</span>
              <input
                type="number"
                min={0}
                value={pending.min_bedrooms ?? ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    min_bedrooms: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  }))
                }
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Max Bedrooms</span>
              <input
                type="number"
                min={0}
                value={pending.max_bedrooms ?? ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    max_bedrooms: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  }))
                }
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Min Bathrooms</span>
              <input
                type="number"
                min={0}
                value={pending.min_bathrooms ?? ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    min_bathrooms: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  }))
                }
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Max Bathrooms</span>
              <input
                type="number"
                min={0}
                value={pending.max_bathrooms ?? ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    max_bathrooms: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  }))
                }
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Min Price</span>
              <input
                type="number"
                min={0}
                step={10000}
                placeholder="e.g. 200000"
                value={pending.min_price ?? ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    min_price: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  }))
                }
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Max Price</span>
              <input
                type="number"
                min={0}
                step={10000}
                placeholder="e.g. 500000"
                value={pending.max_price ?? ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    max_price: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  }))
                }
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Tenure</span>
              <select
                value={pending.tenure || ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    tenure: e.target.value || undefined,
                  }))
                }
                className={inputClass}
              >
                {TENURE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className={labelClass}>EPC Rating</span>
              <select
                value={pending.epc_rating || ""}
                onChange={(e) =>
                  setPending((p) => ({
                    ...p,
                    epc_rating: e.target.value || undefined,
                  }))
                }
                className={inputClass}
              >
                <option value="">Any EPC</option>
                {EPC_RATINGS.slice(1).map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>

            <div className="col-span-2 flex items-end gap-6">
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={pending.has_garden ?? false}
                  onChange={(e) =>
                    setPending((p) => ({
                      ...p,
                      has_garden: e.target.checked || undefined,
                    }))
                  }
                  className="rounded"
                />
                Garden
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={pending.has_parking ?? false}
                  onChange={(e) =>
                    setPending((p) => ({
                      ...p,
                      has_parking: e.target.checked || undefined,
                    }))
                  }
                  className="rounded"
                />
                Parking
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={pending.chain_free ?? false}
                  onChange={(e) =>
                    setPending((p) => ({
                      ...p,
                      chain_free: e.target.checked || undefined,
                    }))
                  }
                  className="rounded"
                />
                Chain Free
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={pending.has_listing ?? false}
                  onChange={(e) =>
                    setPending((p) => ({
                      ...p,
                      has_listing: e.target.checked || undefined,
                    }))
                  }
                  className="rounded"
                />
                Has Current Listing
              </label>
            </div>
          </div>

          <div className="mt-4 flex gap-3">
            <button
              onClick={applyFilters}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              Apply Filters
            </button>
            <button
              onClick={clearFilters}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              Clear All
            </button>
          </div>
        </div>
      )}

      {/* Loading overlay when refetching */}
      {loading && data && (
        <div className="mb-4 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          Updating...
        </div>
      )}

      {/* KPI Cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total Sales"
          value={kpis.total_sales.toLocaleString()}
        />
        <StatCard
          label="Total Properties"
          value={kpis.total_properties.toLocaleString()}
        />
        <StatCard label="Median Price" value={formatPrice(kpis.median_price)} />
        <StatCard
          label="Appreciation Rate"
          value={
            kpis.appreciation_rate != null
              ? `${kpis.appreciation_rate.toFixed(1)}%`
              : "N/A"
          }
        />
        <StatCard
          label="Price / Bedroom"
          value={formatPrice(kpis.price_per_bedroom)}
        />
        <StatCard
          label="Market Velocity"
          value={
            kpis.market_velocity_pct != null
              ? `${kpis.market_velocity_pct > 0 ? "+" : ""}${kpis.market_velocity_pct.toFixed(1)}%`
              : "N/A"
          }
        />
        <StatCard
          label="Velocity Direction"
          value={kpis.market_velocity_direction ?? "N/A"}
        />
        <StatCard
          label="Price Volatility"
          value={
            kpis.price_volatility_pct != null
              ? `${kpis.price_volatility_pct.toFixed(1)}%`
              : "N/A"
          }
        />
      </div>

      {/* Charts Grid */}
      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Price Distribution Histogram */}
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Price Distribution
          </h3>
          {data.price_histogram.length > 0 ? (
            <Plot
              data={[
                {
                  type: "bar",
                  x: data.price_histogram.map((b) => b.range_label),
                  y: data.price_histogram.map((b) => b.count),
                  marker: { color: "#3b82f6" },
                  hovertemplate:
                    "%{x}<br>Count: %{y}<extra></extra>",
                },
              ]}
              layout={{
                paper_bgcolor: "transparent",
                plot_bgcolor: theme.bg,
                font: { color: theme.text, size: 11 },
                xaxis: {
                  gridcolor: theme.grid,
                  tickangle: -45,
                },
                yaxis: {
                  gridcolor: theme.grid,
                  title: { text: "Number of Sales" },
                },
                margin: { t: 10, r: 20, b: 100, l: 60 },
                bargap: 0.1,
              }}
              config={PLOTLY_CONFIG}
              style={{ width: "100%", height: 350 }}
            />
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">
              No price data available
            </p>
          )}
        </div>

        {/* Time Series: Median Price + Sales Volume */}
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Price Trends & Inventory
          </h3>
          {data.time_series.length > 0 ? (
            <Plot
              data={[
                {
                  type: "scatter",
                  mode: "lines",
                  name: "Median Price",
                  x: data.time_series.map((p) => p.month),
                  y: data.time_series.map((p) => p.median_price),
                  line: { color: "#2563eb", width: 2 },
                  hovertemplate:
                    "%{x}<br>Median: \u00a3%{y:,.0f}<extra></extra>",
                },
                {
                  type: "bar",
                  name: "Sales Count",
                  x: data.time_series.map((p) => p.month),
                  y: data.time_series.map((p) => p.sales_count),
                  marker: { color: "rgba(59, 130, 246, 0.3)" },
                  yaxis: "y2",
                  hovertemplate:
                    "%{x}<br>Sales: %{y}<extra></extra>",
                },
              ]}
              layout={{
                paper_bgcolor: "transparent",
                plot_bgcolor: theme.bg,
                font: { color: theme.text, size: 11 },
                xaxis: { gridcolor: theme.grid },
                yaxis: {
                  gridcolor: theme.grid,
                  title: { text: "Median Price (\u00a3)" },
                  tickprefix: "\u00a3",
                  tickformat: ",.0f",
                },
                yaxis2: {
                  overlaying: "y",
                  side: "right",
                  gridcolor: "transparent",
                  title: { text: "Sales Count" },
                },
                margin: { t: 10, r: 60, b: 50, l: 80 },
                legend: {
                  orientation: "h",
                  y: -0.2,
                  font: { color: theme.text },
                },
                showlegend: true,
              }}
              config={PLOTLY_CONFIG}
              style={{ width: "100%", height: 350 }}
            />
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">
              No time series data available
            </p>
          )}
        </div>

        {/* Scatter: Bedrooms vs Price */}
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Bedrooms vs Sale Price
          </h3>
          {data.scatter_data.length > 0 ? (
            <Plot
              data={[
                ...Object.entries(
                  data.scatter_data.reduce<
                    Record<
                      string,
                      { x: number[]; y: number[]; text: string[] }
                    >
                  >((acc, pt) => {
                    const t = pt.property_type || "Unknown";
                    if (!acc[t]) acc[t] = { x: [], y: [], text: [] };
                    acc[t].x.push(pt.bedrooms);
                    acc[t].y.push(pt.price);
                    acc[t].text.push(pt.postcode);
                    return acc;
                  }, {})
                ).map(([type, pts], i) => ({
                  type: "scatter" as const,
                  mode: "markers" as const,
                  name: type,
                  x: pts.x,
                  y: pts.y,
                  text: pts.text,
                  marker: {
                    size: 6,
                    opacity: 0.6,
                    color: SCATTER_COLORS[i % SCATTER_COLORS.length],
                  },
                  hovertemplate:
                    "%{text}<br>Beds: %{x}<br>Price: \u00a3%{y:,.0f}<extra>%{fullData.name}</extra>",
                })),
                ...(trendLine
                  ? [
                      {
                        type: "scatter" as const,
                        mode: "lines" as const,
                        name: "Trend",
                        x: trendLine.x,
                        y: trendLine.y,
                        line: {
                          color: "#ef4444",
                          width: 2,
                          dash: "dash" as const,
                        },
                        hoverinfo: "skip" as const,
                      },
                    ]
                  : []),
              ]}
              layout={{
                paper_bgcolor: "transparent",
                plot_bgcolor: theme.bg,
                font: { color: theme.text, size: 11 },
                xaxis: {
                  gridcolor: theme.grid,
                  title: { text: "Bedrooms" },
                  dtick: 1,
                },
                yaxis: {
                  gridcolor: theme.grid,
                  title: { text: "Sale Price (\u00a3)" },
                  tickprefix: "\u00a3",
                  tickformat: ",.0f",
                },
                margin: { t: 10, r: 20, b: 50, l: 80 },
                legend: {
                  orientation: "h",
                  y: -0.2,
                  font: { color: theme.text },
                },
              }}
              config={PLOTLY_CONFIG}
              style={{ width: "100%", height: 350 }}
            />
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">
              No scatter data available
            </p>
          )}
        </div>

        {/* Postcode Performance Heatmap - clickable bar chart */}
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Postcode Performance
            <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
              Click a bar to filter by area
            </span>
          </h3>
          {data.postcode_heatmap.length > 0 ? (
            <Plot
              data={[
                {
                  type: "bar",
                  orientation: "h",
                  y: data.postcode_heatmap
                    .slice(0, 25)
                    .map((p) => p.postcode),
                  x: data.postcode_heatmap
                    .slice(0, 25)
                    .map((p) => p.avg_price),
                  marker: {
                    color: data.postcode_heatmap.slice(0, 25).map((p) =>
                      p.growth_pct != null
                        ? p.growth_pct > 5
                          ? "#16a34a"
                          : p.growth_pct > 0
                            ? "#84cc16"
                            : p.growth_pct > -5
                              ? "#f59e0b"
                              : "#dc2626"
                        : "#6b7280"
                    ),
                  },
                  text: data.postcode_heatmap.slice(0, 25).map(
                    (p) =>
                      `${p.count} sales${p.growth_pct != null ? `, ${p.growth_pct > 0 ? "+" : ""}${p.growth_pct.toFixed(1)}% growth` : ""}`
                  ),
                  hovertemplate:
                    "%{y}<br>Avg: \u00a3%{x:,.0f}<br>%{text}<extra></extra>",
                },
              ]}
              layout={{
                paper_bgcolor: "transparent",
                plot_bgcolor: theme.bg,
                font: { color: theme.text, size: 11 },
                xaxis: {
                  gridcolor: theme.grid,
                  title: { text: "Average Price (\u00a3)" },
                  tickprefix: "\u00a3",
                  tickformat: ",.0f",
                },
                yaxis: {
                  gridcolor: theme.grid,
                  autorange: "reversed",
                },
                margin: { t: 10, r: 20, b: 50, l: 100 },
              }}
              config={PLOTLY_CONFIG}
              style={{
                width: "100%",
                height: Math.max(
                  350,
                  data.postcode_heatmap.slice(0, 25).length * 24
                ),
              }}
              onClick={(event) => {
                const point = event.points?.[0];
                if (point?.y != null) handlePostcodeClick(String(point.y));
              }}
            />
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">
              No postcode data available
            </p>
          )}
        </div>
      </div>

      {/* Investment Deals Table */}
      <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Investment Opportunities
          <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
            Properties priced below area average
          </span>
        </h3>
        {sortedDeals.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm dark:text-gray-300">
              <thead>
                <tr className="border-b text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
                  {(
                    [
                      { key: "address", label: "Address" },
                      { key: "postcode", label: "Postcode" },
                      { key: "property_type", label: "Type" },
                      { key: "bedrooms", label: "Beds" },
                      { key: "price", label: "Price" },
                      { key: "postcode_avg", label: "Area Avg" },
                      { key: "value_score", label: "Value Score" },
                      { key: "risk_level", label: "Risk" },
                    ] as { key: SortKey; label: string }[]
                  ).map((col) => (
                    <th
                      key={col.key}
                      scope="col"
                      className="cursor-pointer select-none py-2 pr-3 hover:text-gray-700 dark:hover:text-gray-200"
                      onClick={() => handleSort(col.key)}
                    >
                      {col.label}
                      {sortKey === col.key && (
                        <span className="ml-1">
                          {sortAsc ? "\u2191" : "\u2193"}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedDeals.map((deal) => (
                  <tr
                    key={deal.property_id}
                    className="border-b border-gray-100 dark:border-gray-700"
                  >
                    <td className="py-2 pr-3">
                      <Link
                        to={`/property/${deal.property_id}`}
                        className="text-blue-600 hover:underline dark:text-blue-400"
                      >
                        {deal.address}
                      </Link>
                    </td>
                    <td className="py-2 pr-3">{deal.postcode}</td>
                    <td className="py-2 pr-3 capitalize">
                      {deal.property_type?.toLowerCase()}
                    </td>
                    <td className="py-2 pr-3">{deal.bedrooms ?? "\u2014"}</td>
                    <td className="py-2 pr-3 font-medium">
                      {formatPriceFull(deal.price)}
                    </td>
                    <td className="py-2 pr-3 text-gray-500 dark:text-gray-400">
                      {formatPriceFull(deal.postcode_avg)}
                    </td>
                    <td className="py-2 pr-3 font-bold text-green-600 dark:text-green-400">
                      {deal.value_score.toFixed(1)}%
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          deal.risk_level === "Low"
                            ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400"
                            : deal.risk_level === "Medium"
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400"
                              : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400"
                        }`}
                      >
                        {deal.risk_level}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">
            No investment opportunities found with current filters
          </p>
        )}
      </div>
    </div>
  );
}
