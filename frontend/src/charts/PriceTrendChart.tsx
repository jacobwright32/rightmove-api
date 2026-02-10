import { memo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PriceTrendPoint } from "../api/types";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";
import { formatPrice } from "../utils/formatting";

interface Props {
  data: PriceTrendPoint[];
}

export default memo(function PriceTrendChart({ data }: Props) {
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  if (!data.length) return null;

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">Price Trends</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis dataKey="month" tick={{ fontSize: 12, fill: colors.axis }} stroke={colors.grid} />
          <YAxis tickFormatter={(v: number) => formatPrice(v)} width={70} tick={{ fill: colors.axis }} stroke={colors.grid} />
          <Tooltip
            formatter={(v: number) => formatPrice(v)}
            labelFormatter={(l: string) => `Month: ${l}`}
            contentStyle={{ backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, color: colors.text }}
          />
          <Legend wrapperStyle={{ color: colors.text }} />
          <Line
            type="monotone"
            dataKey="avg_price"
            name="Average"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="median_price"
            name="Median"
            stroke="#16a34a"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="max_price"
            name="Max"
            stroke="#dc2626"
            strokeWidth={1}
            strokeDasharray="4 4"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
});
