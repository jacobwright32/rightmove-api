// Matches backend Pydantic schemas

export interface SaleOut {
  id: number;
  date_sold: string | null;
  price: string | null;
  price_numeric: number | null;
  date_sold_iso: string | null;
  price_change_pct: string | null;
  property_type: string | null;
  tenure: string | null;
}

export interface PropertyBrief {
  id: number;
  address: string;
  postcode: string | null;
  property_type: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  floorplan_urls: string | null;
  url: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PropertyDetail extends PropertyBrief {
  extra_features: string | null;
  sales: SaleOut[];
}

export interface ScrapeResponse {
  message: string;
  properties_scraped: number;
  pages_scraped: number;
  detail_pages_visited: number;
}

export interface AreaScrapeResponse {
  message: string;
  postcodes_scraped: string[];
  total_properties: number;
}

export interface PostcodeStatus {
  has_data: boolean;
  property_count: number;
  last_updated: string | null;
}

// Analytics types

export interface PriceTrendPoint {
  month: string;
  avg_price: number | null;
  median_price: number | null;
  min_price: number | null;
  max_price: number | null;
  count: number;
}

export interface PropertyTypeBreakdown {
  property_type: string;
  count: number;
  avg_price: number | null;
}

export interface StreetComparison {
  street: string;
  avg_price: number | null;
  count: number;
}

export interface BedroomDistribution {
  bedrooms: number;
  count: number;
  avg_price: number | null;
}

export interface SalesVolumePoint {
  year: number;
  count: number;
}

export interface PostcodeComparison {
  postcode: string;
  avg_price: number | null;
  count: number;
}

export interface PostcodeAnalytics {
  postcode: string;
  price_trends: PriceTrendPoint[];
  property_types: PropertyTypeBreakdown[];
  street_comparison: StreetComparison[];
  postcode_comparison: PostcodeComparison[];
  bedroom_distribution: BedroomDistribution[];
  sales_volume: SalesVolumePoint[];
}
