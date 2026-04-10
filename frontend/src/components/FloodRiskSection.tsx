import { useEffect, useState } from "react";
import { getFloodRisk } from "../api/client";
import type { FloodRiskResponse } from "../api/types";
import FloodRiskBadge from "./FloodRiskBadge";

interface Props {
  postcode: string;
}

const ZONE_DESCRIPTIONS: Record<number, string> = {
  1: "Flood Zone 1 — Land with a low probability of flooding. Less than 0.1% chance per year.",
  2: "Flood Zone 2 — Land with a medium probability of flooding. Between 0.1% and 1% chance per year.",
  3: "Flood Zone 3 — Land with a high probability of flooding. Greater than 1% chance per year.",
};

export default function FloodRiskSection({ postcode }: Props) {
  const [data, setData] = useState<FloodRiskResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getFloodRisk(postcode)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load flood data");
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
          Flood Risk
        </h3>
        <div className="flex items-center gap-2 text-gray-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
          Checking flood risk...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Flood Risk
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-200">
          Flood Risk
        </h3>
        <FloodRiskBadge riskLevel={data.risk_level} size="md" />
      </div>

      {data.description && (
        <p className="mb-3 text-sm text-gray-600 dark:text-gray-400">
          {data.description}
        </p>
      )}

      {data.flood_zone && (
        <p className="mb-3 text-sm text-gray-500 dark:text-gray-400">
          {ZONE_DESCRIPTIONS[data.flood_zone] ?? `Flood Zone ${data.flood_zone}`}
        </p>
      )}

      {data.active_warnings.length > 0 && (
        <div className="mt-3">
          <h4 className="mb-2 text-sm font-semibold text-red-600 dark:text-red-400">
            Active Warnings ({data.active_warnings.length})
          </h4>
          <div className="space-y-2">
            {data.active_warnings.map((w, i) => (
              <div
                key={i}
                className="rounded-md border border-red-200 bg-red-50 p-2 text-sm dark:border-red-800 dark:bg-red-900/20"
              >
                <div className="font-medium text-red-700 dark:text-red-400">
                  {w.area}
                </div>
                {w.message && (
                  <p className="mt-1 text-red-600 dark:text-red-400 text-xs">
                    {w.message}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
