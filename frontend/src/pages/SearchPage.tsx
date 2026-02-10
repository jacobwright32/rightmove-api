import { useState } from "react";
import { exportSalesData } from "../api/client";
import AnalyticsDashboard from "../components/AnalyticsDashboard";
import LoadingOverlay from "../components/LoadingOverlay";
import SearchBar from "../components/SearchBar";
import ThemeToggle from "../components/ThemeToggle";
import { usePostcodeSearch } from "../hooks/usePostcodeSearch";

export default function SearchPage() {
  const { state, error, result, search, scrapeMessage } = usePostcodeSearch();
  const isLoading = state === "checking" || state === "scraping" || state === "loading";
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  async function handleExport() {
    if (!result.analytics) return;
    setExporting(true);
    setExportMsg(null);
    try {
      const res = await exportSalesData(result.analytics.postcode);
      setExportMsg(res.message);
    } catch (err) {
      setExportMsg(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white shadow-sm dark:bg-gray-800 dark:shadow-gray-900/50">
        <div className="mx-auto max-w-6xl px-4 py-6">
          <div className="flex justify-end"><ThemeToggle /></div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 text-center">
            Rightmove House Prices
          </h1>
          <p className="mt-1 text-center text-gray-500 dark:text-gray-400">
            Enter a postcode to see property sale histories and analytics
          </p>
        </div>
      </header>

      {/* Search */}
      <div className="mx-auto max-w-6xl px-4 py-8">
        <SearchBar onSearch={search} disabled={isLoading} />

        {/* Loading */}
        <LoadingOverlay state={state} />

        {/* Error */}
        {state === "error" && error && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-center text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Results dashboard */}
        {state === "done" && result.analytics && (
          <AnalyticsDashboard
            analytics={result.analytics}
            properties={result.properties}
            scrapeMessage={scrapeMessage}
            exportMsg={exportMsg}
            exporting={exporting}
            onExport={handleExport}
          />
        )}
      </div>
    </div>
  );
}
