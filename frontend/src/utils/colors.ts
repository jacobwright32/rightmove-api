/**
 * Get a Tailwind color class based on where a value falls in a range.
 * Used by heatmap components for price visualization.
 */
export function getColorIntensity(
  value: number,
  min: number,
  max: number
): string {
  if (max === min) return "bg-blue-400";
  const ratio = (value - min) / (max - min);
  if (ratio > 0.8) return "bg-red-500 text-white";
  if (ratio > 0.6) return "bg-orange-400 text-white";
  if (ratio > 0.4) return "bg-yellow-400";
  if (ratio > 0.2) return "bg-green-400";
  return "bg-blue-400 text-white";
}
