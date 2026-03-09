import { useState } from "react";
import { enrichSupermarkets, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

function formatDist(km: number): string {
  return km < 1 ? `${Math.round(km * 1000)}m` : `${km.toFixed(1)} km`;
}

export default function SupermarketsSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasData = property.dist_nearest_supermarket_km != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichSupermarkets(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch supermarket data"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Supermarkets
      </h3>

      {hasData ? (
        <div className="space-y-4">
          {/* Nearest supermarket */}
          <div className="rounded-lg border border-gray-200 p-4 dark:border-gray-600">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Nearest Supermarket
            </div>
            {property.nearest_supermarket_name && (
              <div className="mt-1 font-medium text-gray-800 dark:text-gray-200">
                {property.nearest_supermarket_name}
              </div>
            )}
            {property.nearest_supermarket_brand &&
              property.nearest_supermarket_brand !== property.nearest_supermarket_name && (
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {property.nearest_supermarket_brand}
                </div>
              )}
            <div className="mt-1 text-lg font-bold text-blue-600 dark:text-blue-400">
              {formatDist(property.dist_nearest_supermarket_km!)}
            </div>
          </div>

          {/* Premium / Budget split */}
          <div className="grid gap-3 sm:grid-cols-2">
            {property.dist_nearest_premium_supermarket_km != null && (
              <div className="rounded-lg border border-gray-200 p-3 dark:border-gray-600">
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Nearest Premium
                </div>
                <div className="text-xs text-gray-400 dark:text-gray-500">
                  Waitrose / M&S
                </div>
                <div className="mt-1 text-lg font-bold text-purple-600 dark:text-purple-400">
                  {formatDist(property.dist_nearest_premium_supermarket_km)}
                </div>
              </div>
            )}
            {property.dist_nearest_budget_supermarket_km != null && (
              <div className="rounded-lg border border-gray-200 p-3 dark:border-gray-600">
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Nearest Budget
                </div>
                <div className="text-xs text-gray-400 dark:text-gray-500">
                  Aldi / Lidl
                </div>
                <div className="mt-1 text-lg font-bold text-green-600 dark:text-green-400">
                  {formatDist(property.dist_nearest_budget_supermarket_km)}
                </div>
              </div>
            )}
          </div>

          {/* Count */}
          {property.supermarkets_within_2km != null && (
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="font-medium text-gray-800 dark:text-gray-200">
                {property.supermarkets_within_2km}
              </span>{" "}
              supermarket{property.supermarkets_within_2km !== 1 ? "s" : ""}{" "}
              within 2km
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No supermarket data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              {loading
                ? "Finding nearby supermarkets..."
                : "Find Nearest Supermarkets"}
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
