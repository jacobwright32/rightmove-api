import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getGrowthData } from "../api/client";
import type { PostcodeGrowthResponse } from "../api/types";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";
import { formatPrice, formatPriceFull } from "../utils/formatting";

interface Props {
  postcode: string;
}

export default function GrowthSection({ postcode }: Props) {
  const [data, setData] = useState<PostcodeGrowthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getGrowthData(postcode)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load growth data");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [postcode]);

  if (loading) {
    return (
      <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Capital Growth
        </h3>
        <div className="flex items-center gap-2 text-gray-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
          Loading growth data...
        </div>
      </div>
    );
  }

  if (error || !data || data.data_years === 0) {
    return (
      <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Capital Growth
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {error || "Not enough historical data to calculate growth metrics"}
        </p>
      </div>
    );
  }

  const tooltipStyle = {
    backgroundColor: colors.tooltipBg,
    borderColor: colors.tooltipBorder,
    color: colors.text,
  };

  // Build forecast chart data: historical medians + forecast points
  const chartData = [
    ...data.annual_medians.map((m) => ({
      year: m.year,
      price: m.median_price,
      predicted: null as number | null,
      lower: null as number | null,
      upper: null as number | null,
    })),
    ...data.forecast.map((f) => ({
      year: f.year,
      price: null as number | null,
      predicted: f.predicted_price,
      lower: f.lower_bound,
      upper: f.upper_bound,
    })),
  ];

  // Connect historical to forecast
  if (data.annual_medians.length > 0 && data.forecast.length > 0) {
    const lastHistorical = data.annual_medians[data.annual_medians.length - 1];
    const bridgeIdx = chartData.findIndex((d) => d.year === lastHistorical.year);
    if (bridgeIdx >= 0) {
      chartData[bridgeIdx].predicted = lastHistorical.median_price;
      chartData[bridgeIdx].lower = lastHistorical.median_price;
      chartData[bridgeIdx].upper = lastHistorical.median_price;
    }
  }

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-200">
          Capital Growth
        </h3>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {data.data_years} years of data
        </span>
      </div>

      {/* CAGR badges */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {data.metrics.map((m) => (
          <div
            key={m.period_years}
            className="rounded-lg border p-3 text-center dark:border-gray-600"
          >
            <div
              className={`text-xl font-bold ${
                m.cagr_pct == null
                  ? "text-gray-400"
                  : m.cagr_pct >= 0
                    ? "text-green-600 dark:text-green-400"
                    : "text-red-600 dark:text-red-400"
              }`}
            >
              {m.cagr_pct != null ? `${m.cagr_pct >= 0 ? "+" : ""}${m.cagr_pct.toFixed(1)}%` : "N/A"}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {m.period_years}yr CAGR
            </div>
          </div>
        ))}
      </div>

      {/* Risk metrics */}
      {(data.volatility_pct != null || data.max_drawdown_pct != null) && (
        <div className="mb-4 flex gap-4 text-sm">
          {data.volatility_pct != null && (
            <div className="rounded-md bg-gray-50 px-3 py-1.5 dark:bg-gray-700">
              <span className="text-gray-500 dark:text-gray-400">Volatility: </span>
              <span className="font-semibold text-gray-700 dark:text-gray-200">
                {data.volatility_pct.toFixed(1)}%
              </span>
            </div>
          )}
          {data.max_drawdown_pct != null && (
            <div className="rounded-md bg-gray-50 px-3 py-1.5 dark:bg-gray-700">
              <span className="text-gray-500 dark:text-gray-400">Max Drawdown: </span>
              <span className="font-semibold text-red-600 dark:text-red-400">
                -{data.max_drawdown_pct.toFixed(1)}%
              </span>
            </div>
          )}
        </div>
      )}

      {/* Historical median chart */}
      {data.annual_medians.length > 1 && (
        <div className="mb-4">
          <h4 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
            Median Price by Year{data.forecast.length > 0 ? " + Forecast" : ""}
          </h4>
          <ResponsiveContainer width="100%" height={280}>
            {data.forecast.length > 0 ? (
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                <XAxis dataKey="year" tick={{ fontSize: 12, fill: colors.axis }} stroke={colors.grid} />
                <YAxis tickFormatter={(v: number) => formatPrice(v)} width={70} tick={{ fill: colors.axis }} stroke={colors.grid} />
                <Tooltip
                  formatter={(v: unknown, name: string) =>
                    typeof v === "number" ? [formatPriceFull(v), name] : ["-", name]
                  }
                  contentStyle={tooltipStyle}
                />
                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill="url(#forecastGradient)"
                  connectNulls={false}
                />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="#fff"
                  fillOpacity={dark ? 0 : 0.8}
                  connectNulls={false}
                />
                <Line type="monotone" dataKey="price" name="Historical" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
                <Line type="monotone" dataKey="predicted" name="Forecast" stroke="#3b82f6" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} connectNulls={false} />
              </AreaChart>
            ) : (
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
                <XAxis dataKey="year" tick={{ fontSize: 12, fill: colors.axis }} stroke={colors.grid} />
                <YAxis tickFormatter={(v: number) => formatPrice(v)} width={70} tick={{ fill: colors.axis }} stroke={colors.grid} />
                <Tooltip
                  formatter={(v: number) => formatPriceFull(v)}
                  contentStyle={tooltipStyle}
                />
                <Line type="monotone" dataKey="price" name="Median Price" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
