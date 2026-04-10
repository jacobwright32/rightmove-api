import { useState } from "react";
import { enrichIMD, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

const IMD_DOMAINS = [
  { key: "imd_decile" as const, label: "Overall IMD" },
  { key: "imd_income_decile" as const, label: "Income" },
  { key: "imd_employment_decile" as const, label: "Employment" },
  { key: "imd_education_decile" as const, label: "Education" },
  { key: "imd_health_decile" as const, label: "Health" },
  { key: "imd_crime_decile" as const, label: "Crime" },
  { key: "imd_housing_decile" as const, label: "Housing" },
  { key: "imd_environment_decile" as const, label: "Environment" },
];

function decileColor(decile: number): string {
  // 1 = most deprived (red), 10 = least deprived (green)
  if (decile <= 2) return "bg-red-500 text-white";
  if (decile <= 4) return "bg-orange-400 text-white";
  if (decile <= 6) return "bg-yellow-400 text-gray-800";
  if (decile <= 8) return "bg-green-400 text-white";
  return "bg-green-600 text-white";
}

function decileLabel(decile: number): string {
  if (decile <= 2) return "Most deprived";
  if (decile <= 4) return "More deprived";
  if (decile <= 6) return "Average";
  if (decile <= 8) return "Less deprived";
  return "Least deprived";
}

export default function IMDSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasIMDData = property.imd_decile != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichIMD(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch IMD data"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Deprivation (IMD)
      </h3>

      {hasIMDData ? (
        <>
          <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
            Deciles 1-10: 1 = most deprived 10%, 10 = least deprived 10%
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {IMD_DOMAINS.map(({ key, label }) => {
              const val = property[key];
              if (val == null) return null;
              return (
                <div
                  key={key}
                  className="rounded-lg border border-gray-200 p-3 text-center dark:border-gray-600"
                >
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {label}
                  </div>
                  <div
                    className={`mt-1 inline-block rounded-full px-3 py-1 text-lg font-bold ${decileColor(val)}`}
                  >
                    {val}
                  </div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {decileLabel(val)}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No deprivation data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              {loading ? "Fetching IMD data..." : "Fetch IMD Deprivation Data"}
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
