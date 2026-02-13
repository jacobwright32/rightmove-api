interface Props {
  riskLevel: string | null;
  size?: "sm" | "md";
}

const RISK_COLORS: Record<string, string> = {
  very_low: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  low: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  high: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  unknown: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400",
};

const RISK_LABELS: Record<string, string> = {
  very_low: "Very Low",
  low: "Low",
  medium: "Medium",
  high: "High",
  unknown: "Unknown",
};

export default function FloodRiskBadge({ riskLevel, size = "sm" }: Props) {
  if (!riskLevel) return null;

  const colorClass = RISK_COLORS[riskLevel] ?? RISK_COLORS.unknown;
  const label = RISK_LABELS[riskLevel] ?? riskLevel;
  const sizeClass = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium ${colorClass} ${sizeClass}`}
      title={`Flood risk: ${label}`}
    >
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2C8 8 4 12 4 16a8 8 0 0016 0c0-4-4-8-8-14z" />
      </svg>
      Flood: {label}
    </span>
  );
}
