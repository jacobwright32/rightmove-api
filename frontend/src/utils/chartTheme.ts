export function getChartColors(dark: boolean) {
  return {
    grid: dark ? "#374151" : "#e5e7eb",
    axis: dark ? "#9ca3af" : "#6b7280",
    tooltipBg: dark ? "#1f2937" : "#ffffff",
    tooltipBorder: dark ? "#374151" : "#e5e7eb",
    text: dark ? "#d1d5db" : "#374151",
  };
}
