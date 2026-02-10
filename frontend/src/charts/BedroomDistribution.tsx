import { memo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BedroomDistribution as BedData } from "../api/types";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";
import { formatPrice } from "../utils/formatting";

interface Props {
  data: BedData[];
}

export default memo(function BedroomDistributionChart({ data }: Props) {
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  if (!data.length) return null;

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Bedroom Distribution
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis
            dataKey="bedrooms"
            tickFormatter={(v: number) => `${v} bed`}
            tick={{ fill: colors.axis }}
            stroke={colors.grid}
          />
          <YAxis yAxisId="left" tick={{ fill: colors.axis }} stroke={colors.grid} />
          <YAxis
            yAxisId="right"
            orientation="right"
            tickFormatter={(v: number) => formatPrice(v)}
            width={70}
            tick={{ fill: colors.axis }}
            stroke={colors.grid}
          />
          <Tooltip
            formatter={(value: number, name: string) =>
              name === "Avg Price" ? formatPrice(value) : value
            }
            contentStyle={{ backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, color: colors.text }}
          />
          <Legend wrapperStyle={{ color: colors.text }} />
          <Bar
            yAxisId="left"
            dataKey="count"
            name="Count"
            fill="#2563eb"
            radius={[4, 4, 0, 0]}
          />
          <Bar
            yAxisId="right"
            dataKey="avg_price"
            name="Avg Price"
            fill="#16a34a"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
});
