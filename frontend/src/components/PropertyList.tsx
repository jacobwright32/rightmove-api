import type { PropertyDetail } from "../api/types";
import PropertyCard from "./PropertyCard";

interface Props {
  properties: PropertyDetail[];
}

export default function PropertyList({ properties }: Props) {
  if (!properties.length)
    return <p className="text-center text-gray-400 py-8 dark:text-gray-500">No properties found for this postcode.</p>;

  return (
    <div>
      <h2 className="mb-4 text-xl font-bold text-gray-800 dark:text-gray-200">
        Properties ({properties.length})
      </h2>
      <div className="flex flex-col gap-3 max-h-[600px] overflow-y-auto pr-1">
        {properties.map((p) => (
          <div key={p.id} className="property-item">
            <PropertyCard property={p} />
          </div>
        ))}
      </div>
    </div>
  );
}
