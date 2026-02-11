import { useEffect, useState } from "react";
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
import { getGrowthLeaderboard, getMarketOverview } from "../api/client";
import type { GrowthLeaderboardEntry, MarketOverview } from "../api/types";
import StatCard from "../components/StatCard";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";
import { formatPrice, formatPriceFull } from "../utils/formatting";

export default function MarketOverviewPage() {
  const [data, setData] = useState<MarketOverview | null>(null);
  const [leaderboard, setLeaderboard] = useState<GrowthLeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getMarketOverview(),
      getGrowthLeaderboard(20, 5).catch(() => [] as GrowthLeaderboardEntry[]),
    ])
      .then(([d, lb]) => {
        if (!cancelled) { setData(d); setLeaderboard(lb); }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12 text-center">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
        <p className="mt-3 text-gray-500 dark:text-gray-400">Loading market data...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-400">
          {error || "No data available. Scrape some postcodes first!"}
        </div>
      </div>
    );
  }

  const tooltipStyle = {
    backgroundColor: colors.tooltipBg,
    borderColor: colors.tooltipBorder,
    color: colors.text,
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
        Market Overview
      </h1>

      {/* Summary stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-6">
        <StatCard label="Postcodes" value={String(data.total_postcodes)} />
        <StatCard label="Properties" value={String(data.total_properties)} />
        <StatCard label="Total Sales" value={String(data.total_sales)} />
        <StatCard label="Avg Price" value={formatPrice(data.avg_price)} />
        <StatCard label="Median Price" value={formatPrice(data.median_price)} />
        <StatCard
          label="Date Range"
          value={
            data.date_range.earliest && data.date_range.latest
              ? `${data.date_range.earliest.slice(0, 4)}-${data.date_range.latest.slice(0, 4)}`
              : "N/A"
          }
        />
      </div>

      {/* Price distribution */}
      {data.price_distribution.length > 0 && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Price Distribution
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.price_distribution}>
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis dataKey="range" tick={{ fontSize: 12, fill: colors.axis }} stroke={colors.grid} />
              <YAxis tick={{ fill: colors.axis }} stroke={colors.grid} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Properties" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Price trends */}
      {data.price_trends.length > 0 && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Price Trends (All Areas)
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.price_trends}>
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: colors.axis }} stroke={colors.grid} />
              <YAxis tickFormatter={(v: number) => formatPrice(v)} width={70} tick={{ fill: colors.axis }} stroke={colors.grid} />
              <Tooltip
                formatter={(v: number) => formatPriceFull(v)}
                contentStyle={tooltipStyle}
              />
              <Legend wrapperStyle={{ color: colors.text }} />
              <Line type="monotone" dataKey="avg_price" name="Average" stroke="#2563eb" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="median_price" name="Median" stroke="#16a34a" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Property types */}
        {data.property_types.length > 0 && (
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
              Property Types
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.property_types} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                <XAxis type="number" tick={{ fill: colors.axis }} stroke={colors.grid} />
                <YAxis
                  dataKey="property_type"
                  type="category"
                  width={140}
                  tick={{ fontSize: 12, fill: colors.axis }}
                  stroke={colors.grid}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" name="Count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Bedroom distribution */}
        {data.bedroom_distribution.length > 0 && (
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
              Bedroom Distribution
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.bedroom_distribution}>
                <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                <XAxis dataKey="bedrooms" tick={{ fill: colors.axis }} stroke={colors.grid} />
                <YAxis yAxisId="count" tick={{ fill: colors.axis }} stroke={colors.grid} />
                <YAxis yAxisId="price" orientation="right" tickFormatter={(v: number) => formatPrice(v)} tick={{ fill: colors.axis }} stroke={colors.grid} />
                <Tooltip
                  formatter={(v: number, name: string) =>
                    name === "Avg Price" ? formatPriceFull(v) : v
                  }
                  contentStyle={tooltipStyle}
                />
                <Legend wrapperStyle={{ color: colors.text }} />
                <Bar yAxisId="count" dataKey="count" name="Count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="price" dataKey="avg_price" name="Avg Price" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Sales volume */}
      {data.yearly_trends.length > 0 && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Sales Volume by Year
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.yearly_trends}>
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis dataKey="year" tick={{ fill: colors.axis }} stroke={colors.grid} />
              <YAxis tick={{ fill: colors.axis }} stroke={colors.grid} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" name="Sales" fill="#10b981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top postcodes table */}
      {data.top_postcodes.length > 0 && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Top Postcodes by Sales Volume
          </h3>
          <table className="w-full text-sm dark:text-gray-300">
            <thead>
              <tr className="border-b text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
                <th scope="col" className="py-2 pr-3">#</th>
                <th scope="col" className="py-2 pr-3">Postcode</th>
                <th scope="col" className="py-2 pr-3 text-right">Avg Price</th>
                <th scope="col" className="py-2 text-right">Sales</th>
              </tr>
            </thead>
            <tbody>
              {data.top_postcodes.map((pc, i) => (
                <tr key={pc.postcode} className="border-b border-gray-100 dark:border-gray-700">
                  <td className="py-2 pr-3 text-gray-400">{i + 1}</td>
                  <td className="py-2 pr-3 font-medium">{pc.postcode}</td>
                  <td className="py-2 pr-3 text-right">{formatPriceFull(pc.avg_price)}</td>
                  <td className="py-2 text-right">{pc.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Growth leaderboard */}
      {leaderboard.length > 0 && (
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Growth Leaderboard (5yr CAGR)
          </h3>
          <table className="w-full text-sm dark:text-gray-300">
            <thead>
              <tr className="border-b text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
                <th scope="col" className="py-2 pr-3">#</th>
                <th scope="col" className="py-2 pr-3">Postcode</th>
                <th scope="col" className="py-2 pr-3 text-right">CAGR</th>
                <th scope="col" className="py-2 pr-3 text-right">Latest Median</th>
                <th scope="col" className="py-2 text-right">Years</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((entry, i) => (
                <tr key={entry.postcode} className="border-b border-gray-100 dark:border-gray-700">
                  <td className="py-2 pr-3 text-gray-400">{i + 1}</td>
                  <td className="py-2 pr-3 font-medium">{entry.postcode}</td>
                  <td className={`py-2 pr-3 text-right font-semibold ${entry.cagr_pct >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                    {entry.cagr_pct >= 0 ? "+" : ""}{entry.cagr_pct.toFixed(1)}%
                  </td>
                  <td className="py-2 pr-3 text-right">{formatPriceFull(entry.latest_median)}</td>
                  <td className="py-2 text-right">{entry.data_years}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
