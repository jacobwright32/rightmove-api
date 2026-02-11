import { useState } from "react";
import { Link } from "react-router-dom";
import type { PropertyDetail } from "../api/types";
import EPCBadge from "./EPCBadge";
import FloodRiskBadge from "./FloodRiskBadge";
import SaleHistoryTable from "./SaleHistoryTable";

interface Props {
  property: PropertyDetail;
}

function parseJsonArray(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function PropertyCard({ property }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [floorplanOpen, setFloorplanOpen] = useState(false);
  const sales = property.sales ?? [];
  const features = parseJsonArray(property.extra_features);
  const floorplans = parseJsonArray(property.floorplan_urls);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <button
        type="button"
        className="flex w-full cursor-pointer items-start justify-between text-left focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded dark:focus:ring-offset-gray-800"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={`${property.address} — ${sales.length} sale${sales.length !== 1 ? "s" : ""}. Click to ${expanded ? "collapse" : "expand"}`}
      >
        <div>
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            {property.url ? (
              <a
                href={property.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-600 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                {property.address}
              </a>
            ) : (
              property.address
            )}
          </h3>
          <div className="mt-1 flex flex-wrap gap-3 text-sm text-gray-500 dark:text-gray-400">
            {property.property_type && <span>{property.property_type}</span>}
            {property.bedrooms != null && <span>{property.bedrooms} bed</span>}
            {property.bathrooms != null && (
              <span>{property.bathrooms} bath</span>
            )}
            {floorplans.length > 0 && (
              <span className="text-blue-500">Floorplan</span>
            )}
            {features.length > 0 && (
              <span className="text-green-600">{features.length} features</span>
            )}
            <EPCBadge rating={property.epc_rating} />
            <FloodRiskBadge riskLevel={property.flood_risk_level} />
          </div>
        </div>
        <span className="text-gray-400 text-sm dark:text-gray-500" aria-hidden="true">
          {sales.length} sale{sales.length !== 1 && "s"}{" "}
          {expanded ? "\u25B2" : "\u25BC"}
        </span>
      </button>

      {expanded && (
        <div className="mt-3 border-t pt-3 space-y-4 dark:border-gray-700">
          {/* Extra features */}
          {features.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase text-gray-400 mb-2 dark:text-gray-500">Key Features</h4>
              <div className="flex flex-wrap gap-2">
                {features.map((f, i) => (
                  <span
                    key={i}
                    className="inline-block rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Floorplan images */}
          {floorplans.length > 0 && (
            <div>
              <button
                className="text-xs font-semibold uppercase text-blue-500 hover:text-blue-700 mb-2"
                onClick={() => setFloorplanOpen(!floorplanOpen)}
              >
                Floorplan {floorplanOpen ? "\u25B2" : "\u25BC"}
              </button>
              {floorplanOpen && (
                <div className="flex flex-wrap gap-3">
                  {floorplans.map((url, i) => (
                    <a
                      key={i}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <img
                        src={url}
                        alt={`Floorplan ${i + 1} for ${property.address}`}
                        loading="lazy"
                        className="max-h-64 max-w-full rounded border border-gray-200 hover:shadow-md transition-shadow"
                      />
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Sale history */}
          <SaleHistoryTable sales={sales} />

          {/* Detail page link */}
          <Link
            to={`/property/${property.id}`}
            className="inline-block text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
            onClick={(e) => e.stopPropagation()}
          >
            View full details &rarr;
          </Link>
        </div>
      )}
    </div>
  );
}
