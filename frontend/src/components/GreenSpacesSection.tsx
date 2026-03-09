import { useState } from "react";
import { enrichGreenSpaces, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

function formatDist(km: number): string {
  return km < 1 ? `${Math.round(km * 1000)}m` : `${km.toFixed(1)} km`;
}

export default function GreenSpacesSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasData = property.dist_nearest_green_space_km != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichGreenSpaces(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch green space data"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Green Spaces
      </h3>

      {hasData ? (
        <div className="space-y-4">
          {/* Nearest park */}
          {property.dist_nearest_park_km != null && (
            <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-600">
              <div className="text-sm text-gray-500 dark:text-gray-400">
                Nearest Park
              </div>
              {property.nearest_park_name && (
                <div className="mt-1 font-medium text-gray-800 dark:text-gray-200">
                  {property.nearest_park_name}
                </div>
              )}
              <div className="mt-1 text-lg font-bold text-green-600 dark:text-green-400">
                {formatDist(property.dist_nearest_park_km)}
              </div>
            </div>
          )}

          {/* Nearest green space of any type */}
          <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-600">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Nearest Green Space (any type)
            </div>
            {property.nearest_green_space_name && (
              <div className="mt-1 font-medium text-gray-800 dark:text-gray-200">
                {property.nearest_green_space_name}
              </div>
            )}
            <div className="mt-1 text-lg font-bold text-emerald-600 dark:text-emerald-400">
              {formatDist(property.dist_nearest_green_space_km!)}
            </div>
          </div>

          {/* Count */}
          {property.green_spaces_within_1km != null && (
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="font-medium text-gray-800 dark:text-gray-200">
                {property.green_spaces_within_1km}
              </span>{" "}
              green space{property.green_spaces_within_1km !== 1 ? "s" : ""}{" "}
              within 1km
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No green space data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 dark:bg-green-500 dark:hover:bg-green-600"
            >
              {loading
                ? "Finding nearby green spaces..."
                : "Find Nearest Green Spaces"}
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
