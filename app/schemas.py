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
