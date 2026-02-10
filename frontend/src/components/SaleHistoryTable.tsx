import type { SaleOut } from "../api/types";

interface Props {
  sales: SaleOut[];
}

export default function SaleHistoryTable({ sales }: Props) {
  if (!sales.length) return <p className="text-gray-400 text-sm dark:text-gray-500">No sale history</p>;

  return (
    <table className="w-full text-sm dark:text-gray-300">
      <thead>
        <tr className="border-b text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
          <th scope="col" className="py-1 pr-3">Date</th>
          <th scope="col" className="py-1 pr-3">Price</th>
          <th scope="col" className="py-1 pr-3">Change</th>
          <th scope="col" className="py-1 pr-3">Tenure</th>
        </tr>
      </thead>
      <tbody>
        {sales.map((s) => (
          <tr key={s.id} className="border-b border-gray-100 dark:border-gray-700">
            <td className="py-1 pr-3">{s.date_sold ?? "-"}</td>
            <td className="py-1 pr-3 font-medium">{s.price ?? "-"}</td>
            <td className="py-1 pr-3">{s.price_change_pct || "-"}</td>
            <td className="py-1 pr-3">{s.tenure || "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
