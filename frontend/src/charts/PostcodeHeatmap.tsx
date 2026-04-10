import { memo } from "react";
import type { PostcodeComparison } from "../api/types";
import { getColorIntensity } from "../utils/colors";
import { formatPrice } from "../utils/formatting";

interface Props {
  data: PostcodeComparison[];
}

export default memo(function PostcodeHeatmap({ data }: Props) {
  if (!data.length) return null;

  const prices = data.map((d) => d.avg_price ?? 0).filter((p) => p > 0 && Number.isFinite(p));
  if (!prices.length) return null;
  const min = Math.min(...prices);
  const max = Math.max(...prices);

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Postcode Price Comparison
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        {data.map((pc) => (
          <div
            key={pc.postcode}
            className={`rounded-lg p-3 text-center text-sm ${getColorIntensity(pc.avg_price ?? 0, min, max)}`}
          >
            <div className="font-semibold truncate" title={pc.postcode}>
              {pc.postcode}
            </div>
            <div className="text-xs mt-1">
              {formatPrice(pc.avg_price)} ({pc.count})
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <span className="inline-block h-3 w-3 rounded bg-blue-400" /> Low
        <span className="inline-block h-3 w-3 rounded bg-green-400" />
        <span className="inline-block h-3 w-3 rounded bg-yellow-400" />
        <span className="inline-block h-3 w-3 rounded bg-orange-400" />
        <span className="inline-block h-3 w-3 rounded bg-red-500" /> High
      </div>
    </div>
  );
});
