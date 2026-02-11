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
  epc_rating: string | null;
  epc_score: number | null;
  epc_environment_impact: number | null;
  estimated_energy_cost: number | null;
  flood_risk_level: string | null;
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
  skipped: boolean;
}

export interface AreaScrapeResponse {
  message: string;
  postcodes_scraped: string[];
  postcodes_skipped: string[];
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

// Market Overview types

export interface PriceRangeBucket {
  range: string;
  count: number;
}

export interface MarketOverview {
  total_postcodes: number;
  total_properties: number;
  total_sales: number;
  date_range: { earliest: string | null; latest: string | null };
  avg_price: number | null;
  median_price: number | null;
  price_distribution: PriceRangeBucket[];
  top_postcodes: PostcodeComparison[];
  property_types: PropertyTypeBreakdown[];
  bedroom_distribution: BedroomDistribution[];
  yearly_trends: SalesVolumePoint[];
  price_trends: PriceTrendPoint[];
}

// Housing Insights types

export interface PriceHistogramBucket {
  range_label: string;
  min_price: number;
  max_price: number;
  count: number;
}

export interface InsightsTimeSeriesPoint {
  month: string;
  median_price: number | null;
  sales_count: number;
}

export interface ScatterPoint {
  bedrooms: number;
  price: number;
  postcode: string;
  property_type: string;
}

export interface PostcodeHeatmapPoint {
  postcode: string;
  avg_price: number;
  count: number;
  growth_pct: number | null;
}

export interface KPIData {
  appreciation_rate: number | null;
  price_per_bedroom: number | null;
  market_velocity_pct: number | null;
  market_velocity_direction: string | null;
  price_volatility_pct: number | null;
  total_sales: number;
  total_properties: number;
  median_price: number | null;
}

export interface InvestmentDeal {
  property_id: number;
  address: string;
  postcode: string | null;
  property_type: string | null;
  bedrooms: number | null;
  price: number;
  date_sold: string | null;
  postcode_avg: number;
  value_score: number;
  risk_level: string;
}

export interface HousingInsightsFilters {
  property_type?: string;
  min_bedrooms?: number;
  max_bedrooms?: number;
  min_bathrooms?: number;
  max_bathrooms?: number;
  min_price?: number;
  max_price?: number;
  postcode_prefix?: string;
  tenure?: string;
  epc_rating?: string;
  has_garden?: boolean;
  has_parking?: boolean;
  chain_free?: boolean;
}

export interface HousingInsightsResponse {
  price_histogram: PriceHistogramBucket[];
  time_series: InsightsTimeSeriesPoint[];
  scatter_data: ScatterPoint[];
  postcode_heatmap: PostcodeHeatmapPoint[];
  kpis: KPIData;
  investment_deals: InvestmentDeal[];
  filters_applied: Record<string, unknown>;
}

// EPC Enrichment

export interface EPCEnrichmentResponse {
  message: string;
  properties_updated: number;
  certificates_found: number;
}

// Geo / Map

export interface PropertyGeoPoint {
  id: number;
  address: string;
  postcode: string | null;
  latitude: number;
  longitude: number;
  latest_price: number | null;
  property_type: string | null;
  bedrooms: number | null;
  epc_rating: string | null;
  flood_risk_level: string | null;
}

// Flood Risk

export interface FloodWarning {
  severity: string;
  message: string;
  area: string;
}

export interface FloodRiskResponse {
  postcode: string;
  risk_level: string;
  flood_zone: number | null;
  active_warnings: FloodWarning[];
  description: string;
}

// Growth & Forecasting

export interface AnnualMedian {
  year: number;
  median_price: number;
  sale_count: number;
}

export interface GrowthPeriodMetric {
  period_years: number;
  cagr_pct: number | null;
  start_price: number | null;
  end_price: number | null;
}

export interface GrowthForecastPoint {
  year: number;
  predicted_price: number;
  lower_bound: number;
  upper_bound: number;
}

export interface PostcodeGrowthResponse {
  postcode: string;
  metrics: GrowthPeriodMetric[];
  volatility_pct: number | null;
  max_drawdown_pct: number | null;
  forecast: GrowthForecastPoint[];
  annual_medians: AnnualMedian[];
  data_years: number;
}

export interface GrowthLeaderboardEntry {
  postcode: string;
  cagr_pct: number;
  data_years: number;
  latest_median: number | null;
  sale_count: number;
}

// Crime Data

export interface CrimeMonthlyStat {
  month: string;
  total: number;
}

export interface CrimeSummaryResponse {
  postcode: string;
  categories: Record<string, number>;
  monthly_trend: CrimeMonthlyStat[];
  total_crimes: number;
  months_covered: number;
  cached: boolean;
}
