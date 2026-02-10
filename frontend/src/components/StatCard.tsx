import { memo } from "react";

interface Props {
  label: string;
  value: string;
}

export default memo(function StatCard({ label, value }: Props) {
  return (
    <div className="rounded-lg border bg-white p-4 text-center shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{value}</div>
      <div className="text-sm text-gray-500 dark:text-gray-400">{label}</div>
    </div>
  );
});
