import { useState } from "react";
import { enrichTransport, getProperty } from "../api/client";
import type { PropertyDetail } from "../api/types";

interface Props {
  property: PropertyDetail;
  onRefresh: (updated: PropertyDetail) => void;
}

const TRANSPORT_TYPES = [
  {
    key: "dist_nearest_rail_km" as const,
    nameKey: "nearest_rail_station" as const,
    label: "Rail Station",
    icon: "\uD83D\uDE82",
  },
  {
    key: "dist_nearest_tube_km" as const,
    nameKey: "nearest_tube_station" as const,
    label: "Tube",
    icon: "\uD83D\uDE87",
  },
  {
    key: "dist_nearest_bus_km" as const,
    nameKey: null,
    label: "Bus Stop",
    icon: "\uD83D\uDE8C",
  },
  {
    key: "dist_nearest_airport_km" as const,
    nameKey: "nearest_airport" as const,
    label: "Airport",
    icon: "\u2708\uFE0F",
  },
  {
    key: "dist_nearest_port_km" as const,
    nameKey: "nearest_port" as const,
    label: "Port",
    icon: "\u26F4\uFE0F",
  },
];

export default function TransportSection({ property, onRefresh }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const hasTransportData = property.dist_nearest_rail_km != null;

  const handleEnrich = async () => {
    if (!property.postcode) return;
    setLoading(true);
    setMessage(null);
    try {
      const result = await enrichTransport(property.postcode);
      setMessage(result.message);
      const updated = await getProperty(property.id);
      onRefresh(updated);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Failed to fetch transport data"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Transport Links
      </h3>

      {hasTransportData ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {TRANSPORT_TYPES.map(({ key, nameKey, label, icon }) => {
              const dist = property[key];
              const name = nameKey ? property[nameKey] : null;
              if (dist == null) return null;
              return (
                <div
                  key={key}
                  className="rounded-lg border border-gray-200 p-3 text-center dark:border-gray-600"
                >
                  <div className="text-2xl">{icon}</div>
                  <div className="mt-1 text-lg font-bold text-blue-600 dark:text-blue-400">
                    {dist < 1
                      ? `${Math.round(dist * 1000)}m`
                      : `${dist.toFixed(1)} km`}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {label}
                  </div>
                  {name && (
                    <div className="mt-1 truncate text-xs font-medium text-gray-700 dark:text-gray-300">
                      {name}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {property.bus_stops_within_500m != null && (
            <div className="mt-3 rounded-lg border border-gray-200 p-3 dark:border-gray-600">
              <div className="flex items-center gap-2">
                <span className="text-xl">{"\uD83D\uDE8C"}</span>
                <span className="font-medium text-gray-800 dark:text-gray-200">
                  {property.bus_stops_within_500m} bus stop
                  {property.bus_stops_within_500m !== 1 ? "s" : ""} within 500m
                </span>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No transport distance data yet for this property.
          </p>
          {property.postcode && (
            <button
              onClick={handleEnrich}
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
            >
              {loading
                ? "Computing distances..."
                : "Compute Transport Distances"}
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
