from datetime import datetime
from typing import List, Optional

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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PropertyDetail(PropertyBrief):
    extra_features: Optional[str] = None
    sales: List[SaleOut] = []


# --- Scrape request/response schemas ---

class ScrapeUrlRequest(BaseModel):
    url: str
    floorplan: bool = False


class ScrapeResponse(BaseModel):
    message: str
    properties_scraped: int
    pages_scraped: int = 1
    detail_pages_visited: int = 0


class AreaScrapeResponse(BaseModel):
    message: str
    postcodes_scraped: List[str]
    postcodes_failed: List[str] = []
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
    price_trends: List[PriceTrendPoint] = []
    property_types: List[PropertyTypeBreakdown] = []
    street_comparison: List[StreetComparison] = []
    postcode_comparison: List[PostcodeComparison] = []
    bedroom_distribution: List[BedroomDistribution] = []
    sales_volume: List[SalesVolumePoint] = []
