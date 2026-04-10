import { useState } from "react";
import { enrichGyms, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

function formatDist(km: number): string {
  return km < 1 ? `${Math.round(km * 1000)}m` : `${km.toFixed(1)} km`;
}

export default function GymsSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasData = property.dist_nearest_gym_km != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichGyms(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch gym data"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Gyms & Fitness
      </h3>

      {hasData ? (
        <div className="space-y-4">
          {/* Nearest gym */}
          <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-600">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Nearest Gym / Fitness Centre
            </div>
            {property.nearest_gym_name && (
              <div className="mt-1 font-medium text-gray-800 dark:text-gray-200">
                {property.nearest_gym_name}
              </div>
            )}
            <div className="mt-1 text-lg font-bold text-rose-600 dark:text-rose-400">
              {formatDist(property.dist_nearest_gym_km!)}
            </div>
          </div>

          {/* Count */}
          {property.gyms_within_2km != null && (
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="font-medium text-gray-800 dark:text-gray-200">
                {property.gyms_within_2km}
              </span>{" "}
              gym{property.gyms_within_2km !== 1 ? "s" : ""} within 2km
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No gym data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50 dark:bg-rose-500 dark:hover:bg-rose-600"
            >
              {loading
                ? "Finding nearby gyms..."
                : "Find Nearest Gyms"}
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
