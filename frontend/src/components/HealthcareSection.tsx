import { useState } from "react";
import { enrichHealthcare, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

function formatDist(km: number): string {
  return km < 1 ? `${Math.round(km * 1000)}m` : `${km.toFixed(1)} km`;
}

export default function HealthcareSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasData = property.dist_nearest_gp_km != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichHealthcare(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch healthcare data"
      );
    } finally {
      setLoading(false);
    }
  };

  const facilities = [
    {
      type: "GP Practice",
      dist: property.dist_nearest_gp_km,
      name: property.nearest_gp_name,
      icon: "\uD83C\uDFE5",
    },
    {
      type: "Hospital",
      dist: property.dist_nearest_hospital_km,
      name: property.nearest_hospital_name,
      icon: "\uD83C\uDFE8",
    },
  ];

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Healthcare
      </h3>

      {hasData ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {facilities.map(({ type, dist, name, icon }) => (
              <div
                key={type}
                className="rounded-lg border border-gray-200 p-4 dark:border-gray-600"
              >
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{icon}</span>
                  <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                    Nearest {type}
                  </span>
                </div>
                {name && (
                  <div className="mt-2 font-medium text-gray-800 dark:text-gray-200">
                    {name}
                  </div>
                )}
                {dist != null && (
                  <div className="mt-1 text-lg font-bold text-blue-600 dark:text-blue-400">
                    {formatDist(dist)}
                  </div>
                )}
              </div>
            ))}
          </div>

          {property.gp_practices_within_2km != null && (
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="font-medium text-gray-800 dark:text-gray-200">
                {property.gp_practices_within_2km}
              </span>{" "}
              GP practice{property.gp_practices_within_2km !== 1 ? "s" : ""}{" "}
              within 2km
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No healthcare data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              {loading
                ? "Computing healthcare distances..."
                : "Find Nearest GP & Hospital"}
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
