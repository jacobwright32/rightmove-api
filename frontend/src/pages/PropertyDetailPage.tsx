import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { enrichEPC, getProperty, getSimilarProperties } from "../api/client";
import type { PropertyBrief, PropertyDetail } from "../api/types";
import CrimeSection from "../components/CrimeSection";
import EPCBadge from "../components/EPCBadge";
import FloodRiskBadge from "../components/FloodRiskBadge";
import FloodRiskSection from "../components/FloodRiskSection";
import GrowthSection from "../components/GrowthSection";
import ListingStatusSection from "../components/ListingStatusSection";
import PlanningSection from "../components/PlanningSection";
import SaleHistoryTable from "../components/SaleHistoryTable";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";
import { formatPrice, formatPriceFull } from "../utils/formatting";

function parseJsonArray(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function PropertyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [property, setProperty] = useState<PropertyDetail | null>(null);
  const [similar, setSimilar] = useState<PropertyBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [epcLoading, setEpcLoading] = useState(false);
  const [epcMessage, setEpcMessage] = useState<string | null>(null);
  const dark = useDarkMode();
  const colors = getChartColors(dark);

  const handleEnrichEPC = async () => {
    if (!property?.postcode) return;
    setEpcLoading(true);
    setEpcMessage(null);
    try {
      const result = await enrichEPC(property.postcode);
      setEpcMessage(result.message);
      // Refresh property data to show new EPC fields
      const updated = await getProperty(Number(id));
      setProperty(updated);
    } catch (err) {
      setEpcMessage(err instanceof Error ? err.message : "Failed to fetch EPC data");
    } finally {
      setEpcLoading(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);

    Promise.all([
      getProperty(Number(id)),
      getSimilarProperties(Number(id)).catch(() => [] as PropertyBrief[]),
    ])
      .then(([prop, sim]) => {
        if (!cancelled) {
          setProperty(prop);
          setSimilar(sim);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Property not found");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [id]);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12 text-center">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
        <p className="mt-3 text-gray-500 dark:text-gray-400">Loading property...</p>
      </div>
    );
  }

  if (error || !property) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-400">
          {error || "Property not found"}
        </div>
        <div className="mt-4 text-center">
          <Link to="/" className="text-blue-600 hover:underline dark:text-blue-400">Back to search</Link>
        </div>
      </div>
    );
  }

  const sales = property.sales ?? [];
  const features = parseJsonArray(property.extra_features);
  const floorplans = parseJsonArray(property.floorplan_urls);

  // Build price history chart data (sorted chronologically)
  const priceHistory = sales
    .filter((s) => s.date_sold_iso && s.price_numeric)
    .map((s) => ({
      date: s.date_sold_iso!,
      label: s.date_sold ?? s.date_sold_iso!,
      price: s.price_numeric!,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  // Price appreciation stats
  const firstSale = priceHistory[0];
  const lastSale = priceHistory[priceHistory.length - 1];
  let totalChange: number | null = null;
  let annualizedChange: number | null = null;
  if (priceHistory.length >= 2 && firstSale && lastSale) {
    totalChange = ((lastSale.price - firstSale.price) / firstSale.price) * 100;
    const years =
      (new Date(lastSale.date).getTime() - new Date(firstSale.date).getTime()) /
      (365.25 * 24 * 60 * 60 * 1000);
    if (years > 0) {
      annualizedChange = (Math.pow(lastSale.price / firstSale.price, 1 / years) - 1) * 100;
    }
  }

  const tooltipStyle = {
    backgroundColor: colors.tooltipBg,
    borderColor: colors.tooltipBorder,
    color: colors.text,
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Breadcrumb */}
      <nav className="mb-4 text-sm text-gray-500 dark:text-gray-400">
        <Link to="/" className="hover:text-blue-600 dark:hover:text-blue-400">Search</Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900 dark:text-gray-100">{property.address}</span>
      </nav>

      {/* Header */}
      <div className="mb-6 rounded-lg border bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          {property.address}
        </h1>
        <div className="mt-2 flex flex-wrap gap-3 text-sm text-gray-500 dark:text-gray-400">
          {property.postcode && (
            <span className="rounded-full bg-gray-100 px-3 py-1 font-medium dark:bg-gray-700 dark:text-gray-300">
              {property.postcode}
            </span>
          )}
          {property.property_type && <span>{property.property_type}</span>}
          {property.bedrooms != null && property.bedrooms > 0 && (
            <span>{property.bedrooms} bed</span>
          )}
          {property.bathrooms != null && property.bathrooms > 0 && (
            <span>{property.bathrooms} bath</span>
          )}
          <EPCBadge rating={property.epc_rating} score={property.epc_score} size="md" />
          <FloodRiskBadge riskLevel={property.flood_risk_level} size="md" />
        </div>
        {property.url && (
          <a
            href={property.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            View on Rightmove
          </a>
        )}
      </div>

      {/* Listing status */}
      <div className="mb-6">
        <ListingStatusSection propertyId={property.id} />
      </div>

      {/* Price appreciation stats */}
      {priceHistory.length >= 2 && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-lg border bg-white p-4 text-center shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {formatPriceFull(firstSale?.price)}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400">First Sale ({firstSale?.label})</div>
          </div>
          <div className="rounded-lg border bg-white p-4 text-center shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {formatPriceFull(lastSale?.price)}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Latest Sale ({lastSale?.label})</div>
          </div>
          <div className="rounded-lg border bg-white p-4 text-center shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className={`text-2xl font-bold ${totalChange != null && totalChange >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
              {totalChange != null ? `${totalChange >= 0 ? "+" : ""}${totalChange.toFixed(1)}%` : "N/A"}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Total Change</div>
          </div>
          <div className="rounded-lg border bg-white p-4 text-center shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className={`text-2xl font-bold ${annualizedChange != null && annualizedChange >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
              {annualizedChange != null ? `${annualizedChange >= 0 ? "+" : ""}${annualizedChange.toFixed(1)}%/yr` : "N/A"}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Annualized</div>
          </div>
        </div>
      )}

      {/* Price history chart */}
      {priceHistory.length > 0 && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Price History
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={priceHistory}>
              <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} />
              <XAxis dataKey="label" tick={{ fontSize: 12, fill: colors.axis }} stroke={colors.grid} />
              <YAxis tickFormatter={(v: number) => formatPrice(v)} width={70} tick={{ fill: colors.axis }} stroke={colors.grid} />
              <Tooltip
                formatter={(v: number) => formatPriceFull(v)}
                labelFormatter={(l: string) => `Sold: ${l}`}
                contentStyle={tooltipStyle}
              />
              <Line
                type="monotone"
                dataKey="price"
                name="Sale Price"
                stroke="#2563eb"
                strokeWidth={2}
                dot={{ r: 4, fill: "#2563eb" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Key features */}
      {features.length > 0 && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Key Features
          </h3>
          <div className="flex flex-wrap gap-2">
            {features.map((f, i) => (
              <span
                key={i}
                className="rounded-full bg-blue-50 px-3 py-1 text-sm text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Floorplans */}
      {floorplans.length > 0 && (
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Floorplans
          </h3>
          <div className="flex flex-wrap gap-3">
            {floorplans.map((url, i) => (
              <a key={i} href={url} target="_blank" rel="noopener noreferrer">
                <img
                  src={url}
                  alt={`Floorplan ${i + 1}`}
                  loading="lazy"
                  className="max-h-72 max-w-full rounded border border-gray-200 hover:shadow-md transition-shadow dark:border-gray-600"
                />
              </a>
            ))}
          </div>
        </div>
      )}

      {/* EPC details */}
      <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Energy Performance
        </h3>
        {property.epc_rating ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="text-center">
              <EPCBadge rating={property.epc_rating} score={property.epc_score} size="md" />
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">Energy Rating</div>
            </div>
            {property.epc_score != null && (
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{property.epc_score}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Efficiency Score</div>
              </div>
            )}
            {property.epc_environment_impact != null && (
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600 dark:text-green-400">{property.epc_environment_impact}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Environment Impact</div>
              </div>
            )}
            {property.estimated_energy_cost != null && (
              <div className="text-center">
                <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                  £{property.estimated_energy_cost.toLocaleString()}/yr
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Est. Energy Cost</div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No EPC data yet for this property.
            </p>
            {property.postcode && (
              <button
                onClick={handleEnrichEPC}
                disabled={epcLoading}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-600"
              >
                {epcLoading ? "Fetching EPC data..." : "Fetch EPC Data"}
              </button>
            )}
            {epcMessage && (
              <p className="text-sm text-gray-600 dark:text-gray-400">{epcMessage}</p>
            )}
          </div>
        )}
      </div>

      {/* Sale history table */}
      <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Sale History
        </h3>
        <SaleHistoryTable sales={sales} />
      </div>

      {/* Capital growth */}
      {property.postcode && (
        <div className="mb-6">
          <GrowthSection postcode={property.postcode} />
        </div>
      )}

      {/* Flood risk */}
      {property.postcode && (
        <div className="mb-6">
          <FloodRiskSection postcode={property.postcode} />
        </div>
      )}

      {/* Planning applications */}
      {property.postcode && (
        <div className="mb-6">
          <PlanningSection postcode={property.postcode} />
        </div>
      )}

      {/* Crime statistics */}
      {property.postcode && (
        <div className="mb-6">
          <CrimeSection postcode={property.postcode} />
        </div>
      )}

      {/* Similar properties */}
      {similar.length > 0 && (
        <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
            Similar Properties
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {similar.map((prop) => (
              <Link
                key={prop.id}
                to={`/property/${prop.id}`}
                className="block rounded-lg border border-gray-200 p-3 transition-colors hover:border-blue-300 hover:bg-blue-50 dark:border-gray-600 dark:hover:border-blue-700 dark:hover:bg-blue-900/20"
              >
                <div className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                  {prop.address}
                </div>
                <div className="mt-1 flex gap-2 text-xs text-gray-500 dark:text-gray-400">
                  {prop.property_type && <span>{prop.property_type}</span>}
                  {prop.bedrooms != null && prop.bedrooms > 0 && (
                    <span>{prop.bedrooms} bed</span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
