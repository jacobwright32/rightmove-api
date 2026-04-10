import { useEffect, useState } from "react";
import { getPlanningApplications } from "../api/client";
import type { PlanningApplicationOut } from "../api/types";

const STATUS_COLORS: Record<string, string> = {
  decided: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
};

const TYPE_LABELS: Record<string, string> = {
  full: "Full",
  outline: "Outline",
  householder: "Householder",
  listed_building: "Listed Building",
  tree: "Tree",
  advertisement: "Advertisement",
  change_of_use: "Change of Use",
  other: "Other",
  unknown: "Unknown",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] || STATUS_COLORS.pending;
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status === "decided" ? "Decided" : "Pending"}
    </span>
  );
}

export default function PlanningSection({ postcode }: { postcode: string }) {
  const [applications, setApplications] = useState<PlanningApplicationOut[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [majorCount, setMajorCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showMajorOnly, setShowMajorOnly] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getPlanningApplications(postcode)
      .then((data) => {
        if (!cancelled) {
          setApplications(data.applications);
          setTotalCount(data.total_count);
          setMajorCount(data.major_count);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load planning data");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [postcode]);

  if (loading) {
    return (
      <div className="rounded-lg border bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          Planning Applications
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading planning data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          Planning Applications
        </h3>
        <p className="text-sm text-red-500 dark:text-red-400">{error}</p>
      </div>
    );
  }

  const displayed = showMajorOnly
    ? applications.filter((a) => a.is_major)
    : applications;

  return (
    <div className="rounded-lg border bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Planning Applications
        </h3>
        <div className="flex items-center gap-3">
          {majorCount > 0 && (
            <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900/40 dark:text-red-300">
              {majorCount} major
            </span>
          )}
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {totalCount} total
          </span>
        </div>
      </div>

      {totalCount === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No planning applications found near this postcode.
        </p>
      ) : (
        <>
          {majorCount > 0 && (
            <div className="mb-4">
              <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <input
                  type="checkbox"
                  checked={showMajorOnly}
                  onChange={(e) => setShowMajorOnly(e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
                Show major developments only
              </label>
            </div>
          )}

          <div className="space-y-3 max-h-96 overflow-y-auto">
            {displayed.map((app) => (
              <div
                key={app.reference}
                className={`rounded-md border p-3 ${
                  app.is_major
                    ? "border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/20"
                    : "border-gray-200 dark:border-gray-700"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-gray-500 dark:text-gray-400">
                        {app.reference}
                      </span>
                      <StatusBadge status={app.status} />
                      {app.is_major && (
                        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/40 dark:text-red-300">
                          Major
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                      {app.description || "No description available"}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-400">
                      {TYPE_LABELS[app.application_type] || app.application_type}
                    </span>
                    {app.decision_date && (
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {app.decision_date}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
