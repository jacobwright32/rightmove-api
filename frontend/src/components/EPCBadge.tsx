interface Props {
  rating: string | null;
  score?: number | null;
  size?: "sm" | "md";
}

const RATING_COLORS: Record<string, string> = {
  A: "bg-green-600 text-white",
  B: "bg-green-500 text-white",
  C: "bg-lime-500 text-white",
  D: "bg-yellow-400 text-gray-900",
  E: "bg-amber-500 text-white",
  F: "bg-orange-600 text-white",
  G: "bg-red-600 text-white",
};

export default function EPCBadge({ rating, score, size = "sm" }: Props) {
  if (!rating) return null;

  const colorClass = RATING_COLORS[rating.toUpperCase()] ?? "bg-gray-400 text-white";
  const sizeClass = size === "md" ? "px-3 py-1 text-base" : "px-2 py-0.5 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded font-bold ${colorClass} ${sizeClass}`}
      title={score ? `EPC ${rating} (${score}/100)` : `EPC ${rating}`}
    >
      EPC {rating.toUpperCase()}
      {score != null && size === "md" && (
        <span className="font-normal opacity-80">({score})</span>
      )}
    </span>
  );
}
