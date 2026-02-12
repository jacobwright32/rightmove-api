import { useState } from "react";
import { enrichSchools, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

function ofstedColor(rating: string): string {
  const r = rating.toLowerCase();
  if (r.includes("outstanding")) return "bg-green-600 text-white";
  if (r.includes("good")) return "bg-blue-500 text-white";
  if (r.includes("requires") || r.includes("ri")) return "bg-amber-500 text-white";
  if (r.includes("inadequate")) return "bg-red-600 text-white";
  return "bg-gray-400 text-white";
}

function formatDist(km: number): string {
  return km < 1 ? `${Math.round(km * 1000)}m` : `${km.toFixed(1)} km`;
}

export default function SchoolsSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasData = property.dist_nearest_primary_km != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichSchools(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch schools data"
      );
    } finally {
      setLoading(false);
    }
  };

  const schools = [
    {
      type: "Primary",
      dist: property.dist_nearest_primary_km,
      name: property.nearest_primary_school,
      ofsted: property.nearest_primary_ofsted,
      outstandingDist: property.dist_nearest_outstanding_primary_km,
    },
    {
      type: "Secondary",
      dist: property.dist_nearest_secondary_km,
      name: property.nearest_secondary_school,
      ofsted: property.nearest_secondary_ofsted,
      outstandingDist: property.dist_nearest_outstanding_secondary_km,
    },
  ];

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Schools
      </h3>

      {hasData ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {schools.map(({ type, dist, name, ofsted, outstandingDist }) => (
              <div
                key={type}
                className="rounded-lg border border-gray-200 p-4 dark:border-gray-600"
              >
                <div className="mb-2 text-sm font-medium text-gray-500 dark:text-gray-400">
                  Nearest {type}
                </div>
                {name && (
                  <div className="mb-1 font-medium text-gray-800 dark:text-gray-200">
                    {name}
                  </div>
                )}
                {dist != null && (
                  <div className="mb-2 text-lg font-bold text-blue-600 dark:text-blue-400">
                    {formatDist(dist)}
                  </div>
                )}
                {ofsted && (
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${ofstedColor(ofsted)}`}
                  >
                    {ofsted}
                  </span>
                )}
                {outstandingDist != null && (
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    Outstanding: {formatDist(outstandingDist)} away
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Counts */}
          <div className="flex gap-6 text-sm text-gray-600 dark:text-gray-400">
            {property.primary_schools_within_2km != null && (
              <span>
                <span className="font-medium text-gray-800 dark:text-gray-200">
                  {property.primary_schools_within_2km}
                </span>{" "}
                primary within 2km
              </span>
            )}
            {property.secondary_schools_within_3km != null && (
              <span>
                <span className="font-medium text-gray-800 dark:text-gray-200">
                  {property.secondary_schools_within_3km}
                </span>{" "}
                secondary within 3km
              </span>
            )}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No school distance data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              {loading
                ? "Computing school distances..."
                : "Compute School Distances"}
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
