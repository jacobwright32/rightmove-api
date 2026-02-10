import { memo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SalesVolumePoint } from "../api/types";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";

interface Props {
  data: SalesVolumePoint[];
}

export default memo(function SalesVolumeTimeline({ data }: Props) {
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  if (!data.length) return null;

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Sales Volume Over Time
      </h3>
      <ResponsiveContainer width="100%" height={250}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
          <XAxis dataKey="year" tick={{ fill: colors.axis }} stroke={colors.grid} />
          <YAxis tick={{ fill: colors.axis }} stroke={colors.grid} />
          <Tooltip
            labelFormatter={(l: number) => `Year: ${l}`}
            formatter={(v: number) => [`${v} sales`, "Count"]}
            contentStyle={{ backgroundColor: colors.tooltipBg, borderColor: colors.tooltipBorder, color: colors.text }}
          />
          <Area
            type="monotone"
            dataKey="count"
            stroke="#2563eb"
            fill={dark ? "#1e40af" : "#93c5fd"}
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
});
