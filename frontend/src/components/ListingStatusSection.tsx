import { useEffect, useState } from "react";
import { getPropertyListing } from "../api/client";
import type { PropertyListingResponse } from "../api/types";

interface Props {
  propertyId: number;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  for_sale: {
    bg: "bg-green-100 dark:bg-green-900/30",
    text: "text-green-800 dark:text-green-400",
    label: "For Sale",
  },
  under_offer: {
    bg: "bg-amber-100 dark:bg-amber-900/30",
    text: "text-amber-800 dark:text-amber-400",
    label: "Under Offer",
  },
  sold_stc: {
    bg: "bg-orange-100 dark:bg-orange-900/30",
    text: "text-orange-800 dark:text-orange-400",
    label: "Sold STC",
  },
  not_listed: {
    bg: "bg-gray-100 dark:bg-gray-700",
    text: "text-gray-600 dark:text-gray-400",
    label: "Not Listed",
  },
};

export default function ListingStatusSection({ propertyId }: Props) {
  const [data, setData] = useState<PropertyListingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getPropertyListing(propertyId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to check listing");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [propertyId]);

  if (loading) {
    return (
      <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Listing Status
        </h3>
        <div className="flex items-center gap-2 text-gray-400">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
          Checking Rightmove...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
          Listing Status
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  const status = data.listing_status ?? "not_listed";
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.not_listed;
  const isListed = status !== "not_listed" && status !== null;

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-200">
          Listing Status
        </h3>
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${style.bg} ${style.text}`}>
          {style.label}
        </span>
      </div>

      {isListed ? (
        <div className="space-y-3">
          {/* Price */}
          {data.listing_price_display && (
            <div>
              <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                {data.listing_price_display}
              </div>
            </div>
          )}

          {/* Listed date */}
          {data.listing_date && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Listed: {data.listing_date}
            </p>
          )}

          {/* Link to Rightmove listing */}
          {data.listing_url && (
            <a
              href={data.listing_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-sm text-blue-600 hover:underline dark:text-blue-400"
            >
              View listing on Rightmove
            </a>
          )}
        </div>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          This property is not currently listed for sale on Rightmove.
        </p>
      )}

      {/* Last checked timestamp */}
      {data.listing_checked_at && (
        <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
          Last checked: {new Date(data.listing_checked_at).toLocaleDateString("en-GB", {
            day: "numeric",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
          {data.stale && " (stale)"}
        </p>
      )}
    </div>
  );
}
