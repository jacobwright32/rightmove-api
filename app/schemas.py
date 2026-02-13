from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# --- Sale schemas ---

class SaleOut(BaseModel):
    id: int
    date_sold: Optional[str] = None
    price: Optional[str] = None
    price_numeric: Optional[int] = None
    date_sold_iso: Optional[str] = None
    price_change_pct: Optional[str] = None
    property_type: Optional[str] = None
    tenure: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Property schemas ---

class PropertyBrief(BaseModel):
    id: int
    address: str
    postcode: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floorplan_urls: Optional[str] = None
    url: Optional[str] = None
    epc_rating: Optional[str] = None
    epc_score: Optional[int] = None
    epc_environment_impact: Optional[int] = None
    estimated_energy_cost: Optional[int] = None
    flood_risk_level: Optional[str] = None
    listing_status: Optional[str] = None
    listing_price: Optional[int] = None
    listing_price_display: Optional[str] = None
    listing_date: Optional[str] = None
    listing_url: Optional[str] = None
    listing_checked_at: Optional[datetime] = None
    # Transport distances
    dist_nearest_rail_km: Optional[float] = None
    dist_nearest_tube_km: Optional[float] = None
    dist_nearest_bus_km: Optional[float] = None
    dist_nearest_airport_km: Optional[float] = None
    dist_nearest_port_km: Optional[float] = None
    nearest_rail_station: Optional[str] = None
    nearest_tube_station: Optional[str] = None
    nearest_airport: Optional[str] = None
    nearest_port: Optional[str] = None
    bus_stops_within_500m: Optional[int] = None
    # IMD deprivation
    imd_decile: Optional[int] = None
    imd_income_decile: Optional[int] = None
    imd_employment_decile: Optional[int] = None
    imd_education_decile: Optional[int] = None
    imd_health_decile: Optional[int] = None
    imd_crime_decile: Optional[int] = None
    imd_housing_decile: Optional[int] = None
    imd_environment_decile: Optional[int] = None
    # Broadband
    broadband_median_speed: Optional[float] = None
    broadband_superfast_pct: Optional[float] = None
    broadband_ultrafast_pct: Optional[float] = None
    broadband_full_fibre_pct: Optional[float] = None
    # Schools
    dist_nearest_primary_km: Optional[float] = None
    dist_nearest_secondary_km: Optional[float] = None
    nearest_primary_school: Optional[str] = None
    nearest_secondary_school: Optional[str] = None
    nearest_primary_ofsted: Optional[str] = None
    nearest_secondary_ofsted: Optional[str] = None
    dist_nearest_outstanding_primary_km: Optional[float] = None
    dist_nearest_outstanding_secondary_km: Optional[float] = None
    primary_schools_within_2km: Optional[int] = None
    secondary_schools_within_3km: Optional[int] = None
    # Healthcare
    dist_nearest_gp_km: Optional[float] = None
    nearest_gp_name: Optional[str] = None
    dist_nearest_hospital_km: Optional[float] = None
    nearest_hospital_name: Optional[str] = None
    gp_practices_within_2km: Optional[int] = None
    # Supermarkets
    dist_nearest_supermarket_km: Optional[float] = None
    nearest_supermarket_name: Optional[str] = None
    nearest_supermarket_brand: Optional[str] = None
    dist_nearest_premium_supermarket_km: Optional[float] = None
    dist_nearest_budget_supermarket_km: Optional[float] = None
    supermarkets_within_2km: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PropertyDetail(PropertyBrief):
    extra_features: Optional[str] = None
    sales: list[SaleOut] = []


# --- Scrape request/response schemas ---

class ScrapeUrlRequest(BaseModel):
    url: str
    floorplan: bool = False


class ScrapeResponse(BaseModel):
    message: str
    properties_scraped: int
    pages_scraped: int = 1
    detail_pages_visited: int = 0
    skipped: bool = False
    mode: str = "house_prices"


class AreaScrapeResponse(BaseModel):
    message: str
    postcodes_scraped: list[str]
    postcodes_skipped: list[str] = []
    postcodes_failed: list[str] = []
    total_properties: int


class ScrapePropertyResponse(BaseModel):
    message: str
    property: Optional[PropertyDetail] = None


# --- Postcode summary ---

class PostcodeSummary(BaseModel):
    postcode: str
    property_count: int


# --- Postcode status ---

class PostcodeStatus(BaseModel):
    has_data: bool
    property_count: int
    last_updated: Optional[datetime] = None


# --- Export ---

class ExportResponse(BaseModel):
    message: str
    properties_exported: int
    files_written: int
    output_dir: str


# --- Analytics schemas ---

class PriceTrendPoint(BaseModel):
    month: str
    avg_price: Optional[float] = None
    median_price: Optional[float] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    count: int = 0


class PropertyTypeBreakdown(BaseModel):
    property_type: str
    count: int
    avg_price: Optional[float] = None


class StreetComparison(BaseModel):
    street: str
    avg_price: Optional[float] = None
    count: int = 0


class PostcodeComparison(BaseModel):
    postcode: str
    avg_price: Optional[float] = None
    count: int = 0


class BedroomDistribution(BaseModel):
    bedrooms: int
    count: int
    avg_price: Optional[float] = None


class SalesVolumePoint(BaseModel):
    year: int
    count: int


class PostcodeAnalytics(BaseModel):
    postcode: str
    price_trends: list[PriceTrendPoint] = []
    property_types: list[PropertyTypeBreakdown] = []
    street_comparison: list[StreetComparison] = []
    postcode_comparison: list[PostcodeComparison] = []
    bedroom_distribution: list[BedroomDistribution] = []
    sales_volume: list[SalesVolumePoint] = []


class PriceRangeBucket(BaseModel):
    range: str
    count: int


class RecentSale(BaseModel):
    property_id: int
    address: str
    postcode: Optional[str] = None
    price: int
    date_sold: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None


class MarketOverview(BaseModel):
    total_postcodes: int
    total_properties: int
    total_sales: int
    date_range: dict
    avg_price: Optional[float] = None
    median_price: Optional[float] = None
    price_distribution: list[PriceRangeBucket] = []
    top_postcodes: list[PostcodeComparison] = []
    property_types: list[PropertyTypeBreakdown] = []
    bedroom_distribution: list[BedroomDistribution] = []
    yearly_trends: list[SalesVolumePoint] = []
    price_trends: list[PriceTrendPoint] = []
    recent_sales: list[RecentSale] = []


# --- Housing Insights schemas ---

class PriceHistogramBucket(BaseModel):
    range_label: str
    min_price: int
    max_price: int
    count: int


class InsightsTimeSeriesPoint(BaseModel):
    month: str
    median_price: Optional[float] = None
    sales_count: int = 0


class ScatterPoint(BaseModel):
    bedrooms: int
    price: int
    postcode: str
    property_type: str


class PostcodeHeatmapPoint(BaseModel):
    postcode: str
    avg_price: float
    count: int
    growth_pct: Optional[float] = None


class KPIData(BaseModel):
    appreciation_rate: Optional[float] = None
    price_per_bedroom: Optional[float] = None
    market_velocity_pct: Optional[float] = None
    market_velocity_direction: Optional[str] = None
    price_volatility_pct: Optional[float] = None
    total_sales: int = 0
    total_properties: int = 0
    median_price: Optional[float] = None


class InvestmentDeal(BaseModel):
    property_id: int
    address: str
    postcode: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    price: int
    date_sold: Optional[str] = None
    postcode_avg: float
    value_score: float
    risk_level: str


class HousingInsightsResponse(BaseModel):
    price_histogram: list[PriceHistogramBucket] = []
    time_series: list[InsightsTimeSeriesPoint] = []
    scatter_data: list[ScatterPoint] = []
    postcode_heatmap: list[PostcodeHeatmapPoint] = []
    kpis: KPIData = KPIData()
    investment_deals: list[InvestmentDeal] = []
    filters_applied: dict = {}


# --- EPC Enrichment schemas ---

class EPCEnrichmentResponse(BaseModel):
    message: str
    properties_updated: int
    certificates_found: int


# --- Transport Enrichment schemas ---


class TransportEnrichmentResponse(BaseModel):
    message: str
    properties_updated: int
    properties_skipped: int


# --- Geo schemas ---


class PropertyGeoPoint(BaseModel):
    id: int
    address: str
    postcode: Optional[str] = None
    latitude: float
    longitude: float
    latest_price: Optional[int] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    epc_rating: Optional[str] = None
    flood_risk_level: Optional[str] = None


# --- Flood Risk schemas ---


class FloodWarning(BaseModel):
    severity: str
    message: str
    area: str


class FloodRiskResponse(BaseModel):
    postcode: str
    risk_level: str  # very_low, low, medium, high, unknown
    flood_zone: Optional[int] = None
    active_warnings: list[FloodWarning] = []
    description: str = ""


# --- Growth & Forecasting schemas ---


class AnnualMedian(BaseModel):
    year: int
    median_price: float
    sale_count: int = 0


class GrowthPeriodMetric(BaseModel):
    period_years: int
    cagr_pct: Optional[float] = None
    start_price: Optional[float] = None
    end_price: Optional[float] = None


class GrowthForecastPoint(BaseModel):
    year: int
    predicted_price: float
    lower_bound: float
    upper_bound: float


class PostcodeGrowthResponse(BaseModel):
    postcode: str
    metrics: list[GrowthPeriodMetric] = []
    volatility_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    forecast: list[GrowthForecastPoint] = []
    annual_medians: list[AnnualMedian] = []
    data_years: int = 0


class GrowthLeaderboardEntry(BaseModel):
    postcode: str
    cagr_pct: float
    data_years: int
    latest_median: Optional[float] = None
    sale_count: int = 0


# --- Planning schemas ---


class PlanningApplicationOut(BaseModel):
    reference: str
    description: str = ""
    status: str = "pending"
    decision_date: Optional[str] = None
    application_type: str = "other"
    is_major: bool = False


class PlanningResponse(BaseModel):
    postcode: str
    applications: list[PlanningApplicationOut] = []
    total_count: int = 0
    major_count: int = 0
    cached: bool = False


# --- Listing status schemas ---


class PropertyListingResponse(BaseModel):
    property_id: int
    listing_status: Optional[str] = None
    listing_price: Optional[int] = None
    listing_price_display: Optional[str] = None
    listing_date: Optional[str] = None
    listing_url: Optional[str] = None
    listing_checked_at: Optional[datetime] = None
    stale: bool = False


class ListingEnrichmentResponse(BaseModel):
    postcode: str
    listings_found: int
    properties_matched: int
    properties_not_listed: int
    cached: bool = False


# --- Crime schemas ---

class CrimeMonthlyStat(BaseModel):
    month: str
    total: int


class CrimeSummaryResponse(BaseModel):
    postcode: str
    categories: dict[str, int] = {}
    monthly_trend: list[CrimeMonthlyStat] = []
    total_crimes: int = 0
    months_covered: int = 0
    cached: bool = False


# --- Modelling schemas ---


class FeatureInfo(BaseModel):
    name: str
    category: str
    label: str
    dtype: str


class TargetInfo(BaseModel):
    name: str
    label: str


class AvailableFeaturesResponse(BaseModel):
    features: list[FeatureInfo] = []
    targets: list[TargetInfo] = []
    total_properties_with_sales: int = 0


class TrainRequest(BaseModel):
    target: str
    features: list[str]
    model_type: str = "lightgbm"
    split_strategy: str = "random"
    split_params: dict = {}
    hyperparameters: Optional[dict] = None
    log_transform: bool = False


class ModelMetrics(BaseModel):
    r_squared: float
    rmse: float
    mae: float
    mape: float


class FeatureImportance(BaseModel):
    feature: str
    importance: float


class PredictionPoint(BaseModel):
    actual: float
    predicted: float
    residual: float
    property_id: int
    address: str


class TrainResponse(BaseModel):
    model_id: str
    metrics: ModelMetrics
    feature_importances: list[FeatureImportance] = []
    predictions: list[PredictionPoint] = []
    train_size: int
    test_size: int


class SinglePredictionResponse(BaseModel):
    property_id: int
    address: str
    predicted_value: float


class PostcodePredictionItem(BaseModel):
    property_id: int
    address: str
    predicted_value: float
    last_sale_price: Optional[float] = None
    difference: Optional[float] = None
    difference_pct: Optional[float] = None


class PostcodePredictionResponse(BaseModel):
    postcode: str
    count: int
    predictions: list


# --- New enrichment response schemas ---


class IMDEnrichmentResponse(BaseModel):
    message: str
    properties_updated: int
    properties_skipped: int


class BroadbandEnrichmentResponse(BaseModel):
    message: str
    properties_updated: int
    properties_skipped: int


class SchoolsEnrichmentResponse(BaseModel):
    message: str
    properties_updated: int
    properties_skipped: int


class HealthcareEnrichmentResponse(BaseModel):
    message: str
    properties_updated: int
    properties_skipped: int


class SupermarketsEnrichmentResponse(BaseModel):
    message: str
    properties_updated: int
    properties_skipped: int
