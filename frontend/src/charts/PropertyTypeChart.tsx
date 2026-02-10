import { memo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PropertyTypeBreakdown } from "../api/types";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";
import { formatPrice } from "../utils/formatting";

const COLORS = ["#2563eb", "#16a34a", "#dc2626", "#f59e0b", "#8b5cf6", "#ec4899"];

interface Props {
  data: PropertyTypeBreakdown[];
}

export default memo(function PropertyTypeChart({ data }: Props) {
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  if (!data.length) return null;

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Property Types
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Pie chart: counts */}
        <ResponsiveContainer width="100%" height={250}>
          <PieChart>
            <Pie
              data={data}
              dataKey="count"
              nameKey="property_type"
              cx="50%"
              cy="50%"
              outerRadius={90}
              label={({ property_type, percent }: { property_type: string; percent: number }) =>
                `${property_type} ${(percent * 100).toFixed(0)}%`
              }
              labelLine={false}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, color: colors.text }}
            />
            <Legend wrapperStyle={{ color: colors.text }} />
          </PieChart>
        </ResponsiveContainer>

        {/* Bar chart: avg prices */}
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
            <XAxis dataKey="property_type" tick={{ fontSize: 11, fill: colors.axis }} stroke={colors.grid} />
            <YAxis tickFormatter={(v: number) => formatPrice(v)} width={70} tick={{ fill: colors.axis }} stroke={colors.grid} />
            <Tooltip
              formatter={(v: number) => formatPrice(v)}
              contentStyle={{ backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, color: colors.text }}
            />
            <Bar dataKey="avg_price" name="Avg Price" fill="#2563eb" radius={[4, 4, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
});
