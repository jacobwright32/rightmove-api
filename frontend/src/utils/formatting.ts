export function formatPrice(value: number | null | undefined): string {
  if (value == null) return "N/A";
  if (value >= 1_000_000) {
    return `\u00a3${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `\u00a3${Math.round(value / 1_000)}K`;
  }
  return `\u00a3${value.toLocaleString()}`;
}

export function formatPriceFull(value: number | null | undefined): string {
  if (value == null) return "N/A";
  return `\u00a3${value.toLocaleString()}`;
}

export function normalisePostcode(input: string): string {
  return input.toUpperCase().replace(/[\s-]/g, "");
}
