import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import { getPropertiesGeo } from "../api/client";
import type { PropertyGeoPoint } from "../api/types";
import { formatPriceFull } from "../utils/formatting";

// Default center: London
const DEFAULT_CENTER: [number, number] = [51.5074, -0.1278];
const DEFAULT_ZOOM = 11;

function createColoredIcon(color: string) {
  return L.divIcon({
    className: "",
    html: `<div style="background:${color};width:14px;height:14px;border-radius:50%;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.3)"></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function getPriceColor(price: number | null, quartiles: number[]): string {
  if (price == null || quartiles.length < 3) return "#9CA3AF"; // gray
  if (price <= quartiles[0]) return "#22C55E"; // green - cheapest
  if (price <= quartiles[1]) return "#EAB308"; // yellow
  if (price <= quartiles[2]) return "#F97316"; // orange
  return "#EF4444"; // red - most expensive
}

function computeQuartiles(prices: number[]): number[] {
  if (prices.length === 0) return [];
  const sorted = [...prices].sort((a, b) => a - b);
  return [
    sorted[Math.floor(sorted.length * 0.25)],
    sorted[Math.floor(sorted.length * 0.5)],
    sorted[Math.floor(sorted.length * 0.75)],
  ];
}

export default function MapViewPage() {
  const [properties, setProperties] = useState<PropertyGeoPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getPropertiesGeo(filter || undefined, 1000)
      .then((data) => {
        if (!cancelled) setProperties(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load map data");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [filter]);

  const quartiles = useMemo(() => {
    const prices = properties
      .map((p) => p.latest_price)
      .filter((p): p is number => p != null);
    return computeQuartiles(prices);
  }, [properties]);

  // Compute center from data
  const center = useMemo((): [number, number] => {
    if (properties.length === 0) return DEFAULT_CENTER;
    const avgLat = properties.reduce((s, p) => s + p.latitude, 0) / properties.length;
    const avgLng = properties.reduce((s, p) => s + p.longitude, 0) / properties.length;
    return [avgLat, avgLng];
  }, [properties]);

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col">
      {/* Filter bar */}
      <div className="flex items-center gap-3 border-b bg-white px-4 py-2 dark:border-gray-700 dark:bg-gray-800">
        <input
          type="text"
          placeholder="Filter by postcode..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-48 rounded border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
        />
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {loading ? "Loading..." : `${properties.length} properties`}
        </span>
        {/* Legend */}
        <div className="ml-auto flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-green-500" /> Lowest
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-yellow-500" /> Low-Mid
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-orange-500" /> Mid-High
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-red-500" /> Highest
          </span>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 px-4 py-2 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Map */}
      <div className="flex-1">
        <MapContainer
          center={center}
          zoom={DEFAULT_ZOOM}
          className="h-full w-full"
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MarkerClusterGroup chunkedLoading>
            {properties.map((p) => (
              <Marker
                key={p.id}
                position={[p.latitude, p.longitude]}
                icon={createColoredIcon(getPriceColor(p.latest_price, quartiles))}
              >
                <Popup>
                  <div className="min-w-[200px]">
                    <div className="font-semibold text-sm">{p.address}</div>
                    <div className="mt-1 text-xs text-gray-600">
                      {p.postcode && <span>{p.postcode}</span>}
                      {p.property_type && <span> &middot; {p.property_type}</span>}
                      {p.bedrooms != null && <span> &middot; {p.bedrooms} bed</span>}
                    </div>
                    {p.latest_price && (
                      <div className="mt-1 font-bold text-blue-600">
                        {formatPriceFull(p.latest_price)}
                      </div>
                    )}
                    <Link
                      to={`/property/${p.id}`}
                      className="mt-2 inline-block text-xs text-blue-600 hover:underline"
                    >
                      View details &rarr;
                    </Link>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MarkerClusterGroup>
        </MapContainer>
      </div>
    </div>
  );
}
