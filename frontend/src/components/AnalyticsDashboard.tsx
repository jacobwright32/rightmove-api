import { memo } from "react";
import type { PostcodeAnalytics, PropertyDetail } from "../api/types";
import BedroomDistributionChart from "../charts/BedroomDistribution";
import PostcodeHeatmap from "../charts/PostcodeHeatmap";
import PriceHeatmap from "../charts/PriceHeatmap";
import PriceTrendChart from "../charts/PriceTrendChart";
import PropertyTypeChart from "../charts/PropertyTypeChart";
import SalesVolumeTimeline from "../charts/SalesVolumeTimeline";
import PropertyList from "./PropertyList";
import StatCard from "./StatCard";

interface Props {
  analytics: PostcodeAnalytics;
  properties: PropertyDetail[];
  scrapeMessage: string | null;
  exportMsg: string | null;
  exporting: boolean;
  onExport: () => void;
}

export default memo(function AnalyticsDashboard({
  analytics,
  properties,
  scrapeMessage,
  exportMsg,
  exporting,
  onExport,
}: Props) {
  return (
    <div className="mt-8 flex flex-col gap-6">
      {/* Scrape summary + save */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1">
          {scrapeMessage && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-center text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
              {scrapeMessage}
            </div>
          )}
        </div>
        <button
          onClick={onExport}
          disabled={exporting}
          className="shrink-0 rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors dark:bg-green-700 dark:hover:bg-green-600"
        >
          {exporting ? "Saving..." : "Save to Parquet"}
        </button>
      </div>
      {exportMsg && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-center text-sm text-green-700 dark:border-green-800 dark:bg-green-900/30 dark:text-green-400">
          {exportMsg}
        </div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Properties" value={String(properties.length)} />
        <StatCard
          label="Total Sales"
          value={String(
            analytics.sales_volume.reduce((s, v) => s + v.count, 0)
          )}
        />
        <StatCard
          label="Property Types"
          value={String(analytics.property_types.length)}
        />
        <StatCard
          label="Streets"
          value={String(analytics.street_comparison.length)}
        />
      </div>

      {/* Charts */}
      <PriceTrendChart data={analytics.price_trends} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <PropertyTypeChart data={analytics.property_types} />
        <BedroomDistributionChart data={analytics.bedroom_distribution} />
      </div>

      <SalesVolumeTimeline data={analytics.sales_volume} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <PriceHeatmap data={analytics.street_comparison} />
        <PostcodeHeatmap data={analytics.postcode_comparison} />
      </div>

      {/* Property list */}
      <PropertyList properties={properties} />
    </div>
  );
});
