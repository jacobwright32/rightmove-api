import { useState } from "react";
import { enrichBroadband, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

function speedColor(speed: number): string {
  if (speed >= 100) return "text-green-600 dark:text-green-400";
  if (speed >= 30) return "text-blue-600 dark:text-blue-400";
  if (speed >= 10) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

function pctBarColor(pct: number): string {
  if (pct >= 80) return "bg-green-500";
  if (pct >= 50) return "bg-blue-500";
  if (pct >= 20) return "bg-yellow-500";
  return "bg-red-500";
}

export default function BroadbandSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasData = property.broadband_median_speed != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichBroadband(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch broadband data"
      );
    } finally {
      setLoading(false);
    }
  };

  const pctMetrics = [
    { key: "broadband_superfast_pct" as const, label: "Superfast (30+ Mbit/s)" },
    { key: "broadband_ultrafast_pct" as const, label: "Ultrafast (300+ Mbit/s)" },
    { key: "broadband_full_fibre_pct" as const, label: "Full Fibre (FTTP)" },
  ];

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Broadband
      </h3>

      {hasData ? (
        <div className="space-y-4">
          {/* Median speed hero */}
          <div className="rounded-lg border border-gray-200 p-4 text-center dark:border-gray-600">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Median Download Speed
            </div>
            <div
              className={`mt-1 text-3xl font-bold ${speedColor(property.broadband_median_speed!)}`}
            >
              {property.broadband_median_speed!.toFixed(1)}
              <span className="ml-1 text-base font-normal text-gray-500 dark:text-gray-400">
                Mbit/s
              </span>
            </div>
          </div>

          {/* Percentage bars */}
          <div className="space-y-3">
            {pctMetrics.map(({ key, label }) => {
              const val = property[key];
              if (val == null) return null;
              return (
                <div key={key}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-300">
                      {label}
                    </span>
                    <span className="font-medium text-gray-800 dark:text-gray-200">
                      {val.toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-600">
                    <div
                      className={`h-full rounded-full ${pctBarColor(val)}`}
                      style={{ width: `${Math.min(val, 100)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No broadband data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              {loading ? "Fetching broadband data..." : "Fetch Broadband Data"}
            </button>
          )}
          {message && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
