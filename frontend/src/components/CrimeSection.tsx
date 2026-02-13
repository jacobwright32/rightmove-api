import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCrimeData } from "../api/client";
import type { CrimeSummaryResponse } from "../api/types";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";

interface Props {
  postcode: string;
}

const PIE_COLORS = [
  "#3B82F6", "#EF4444", "#F59E0B", "#10B981", "#8B5CF6",
  "#EC4899", "#06B6D4", "#F97316", "#6366F1", "#14B8A6",
];

const CATEGORY_LABELS: Record<string, string> = {
  "anti-social-behaviour": "Anti-social behaviour",
  "bicycle-theft": "Bicycle theft",
  burglary: "Burglary",
  "criminal-damage-arson": "Criminal damage & arson",
  drugs: "Drugs",
  "other-crime": "Other crime",
  "other-theft": "Other theft",
  "possession-of-weapons": "Weapons possession",
  "public-order": "Public order",
  robbery: "Robbery",
  shoplifting: "Shoplifting",
  "theft-from-the-person": "Theft from person",
  "vehicle-crime": "Vehicle crime",
  "violent-crime": "Violence & sexual offences",
};

function formatCategory(cat: string): string {
  return CATEGORY_LABELS[cat] ?? cat.replace(/-/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export default function CrimeSection({ postcode }: Props) {
  const [data, setData] = useState<CrimeSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getCrimeData(postcode)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load crime data");
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
          Crime Statistics
        </h3>
        <div className="flex items-center gap-2 text-gray-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
          Loading crime data...
        </div>
      </div>
    );
  }

  if (error || !data || data.total_crimes === 0) {
    return (
      <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Crime Statistics
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {error || "No crime data available for this area"}
        </p>
      </div>
    );
  }

  const categoryData = Object.entries(data.categories)
    .map(([cat, count]) => ({ name: formatCategory(cat), value: count, key: cat }))
    .slice(0, 10);

  const tooltipStyle = {
    backgroundColor: colors.tooltipBg,
    borderColor: colors.tooltipBorder,
    color: colors.text,
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-200">
          Crime Statistics
        </h3>
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <span>{data.total_crimes.toLocaleString()} crimes</span>
          <span className="text-xs">({data.months_covered} months)</span>
          {data.cached && (
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-gray-700">cached</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Crime breakdown pie chart */}
        <div>
          <h4 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
            By Category
          </h4>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={categoryData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={2}
                label={({ name, percent }) =>
                  percent > 0.05 ? `${name.split(" ")[0]} ${(percent * 100).toFixed(0)}%` : ""
                }
                labelLine={false}
                fontSize={11}
              >
                {categoryData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Crime categories bar chart */}
        <div>
          <h4 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
            Top Categories
          </h4>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={categoryData.slice(0, 7)} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis type="number" tick={{ fontSize: 11, fill: colors.axis }} stroke={colors.grid} />
              <YAxis
                type="category"
                dataKey="name"
                width={140}
                tick={{ fontSize: 11, fill: colors.axis }}
                stroke={colors.grid}
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" name="Incidents" radius={[0, 4, 4, 0]}>
                {categoryData.slice(0, 7).map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Monthly trend */}
      {data.monthly_trend.length > 1 && (
        <div className="mt-4">
          <h4 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">
            Monthly Trend
          </h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.monthly_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis
                dataKey="month"
                tick={{ fontSize: 11, fill: colors.axis }}
                stroke={colors.grid}
              />
              <YAxis tick={{ fontSize: 11, fill: colors.axis }} stroke={colors.grid} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line
                type="monotone"
                dataKey="total"
                name="Total Crimes"
                stroke="#EF4444"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
