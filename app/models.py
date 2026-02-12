from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, unique=True, nullable=False)
    postcode = Column(String, index=True)
    property_type = Column(String)
    bedrooms = Column(Integer)
    bathrooms = Column(Integer)
    extra_features = Column(Text)  # JSON array of feature strings
    floorplan_urls = Column(Text)  # JSON array of floorplan image URLs
    url = Column(String)
    # EPC data (populated via /enrich/epc endpoint)
    epc_rating = Column(String, nullable=True)  # A-G
    epc_score = Column(Integer, nullable=True)  # 1-100
    epc_environment_impact = Column(Integer, nullable=True)
    estimated_energy_cost = Column(Integer, nullable=True)  # Annual £
    # Flood risk (populated via flood assessment endpoint)
    flood_risk_level = Column(String, nullable=True)  # very_low/low/medium/high
    # Listing status (populated via listing check endpoint)
    listing_status = Column(String, nullable=True)  # for_sale/under_offer/sold_stc/not_listed
    listing_price = Column(Integer, nullable=True)  # Numeric asking price
    listing_price_display = Column(String, nullable=True)  # "Guide Price £450,000"
    listing_date = Column(String, nullable=True)  # When listed, e.g. "16th January 2026"
    listing_url = Column(String, nullable=True)  # Rightmove for-sale page URL
    listing_checked_at = Column(DateTime, nullable=True)  # Last check timestamp
    # Geocoded coordinates (populated via /properties/geo endpoint)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # Transport distances (populated via /enrich/transport endpoint)
    dist_nearest_rail_km = Column(Float, nullable=True)
    dist_nearest_tube_km = Column(Float, nullable=True)
    dist_nearest_tram_km = Column(Float, nullable=True)
    dist_nearest_bus_km = Column(Float, nullable=True)
    dist_nearest_airport_km = Column(Float, nullable=True)
    dist_nearest_port_km = Column(Float, nullable=True)
    nearest_rail_station = Column(String, nullable=True)
    nearest_tube_station = Column(String, nullable=True)
    nearest_airport = Column(String, nullable=True)
    nearest_port = Column(String, nullable=True)
    bus_stops_within_500m = Column(Integer, nullable=True)
    # IMD (Indices of Multiple Deprivation) — populated via /enrich/imd endpoint
    imd_decile = Column(Integer, nullable=True)  # 1-10, 1 = most deprived
    imd_income_decile = Column(Integer, nullable=True)
    imd_employment_decile = Column(Integer, nullable=True)
    imd_education_decile = Column(Integer, nullable=True)
    imd_health_decile = Column(Integer, nullable=True)
    imd_crime_decile = Column(Integer, nullable=True)
    imd_housing_decile = Column(Integer, nullable=True)
    imd_environment_decile = Column(Integer, nullable=True)
    # Broadband (Ofcom) — populated via /enrich/broadband endpoint
    broadband_median_speed = Column(Float, nullable=True)  # Mbit/s
    broadband_superfast_pct = Column(Float, nullable=True)  # % with 30Mbit/s+
    broadband_ultrafast_pct = Column(Float, nullable=True)  # % with 300Mbit/s+
    broadband_full_fibre_pct = Column(Float, nullable=True)  # % full fibre
    # Schools (GIAS/Ofsted) — populated via /enrich/schools endpoint
    dist_nearest_primary_km = Column(Float, nullable=True)
    dist_nearest_secondary_km = Column(Float, nullable=True)
    nearest_primary_school = Column(String, nullable=True)
    nearest_secondary_school = Column(String, nullable=True)
    nearest_primary_ofsted = Column(String, nullable=True)  # Outstanding/Good/RI/Inadequate
    nearest_secondary_ofsted = Column(String, nullable=True)
    dist_nearest_outstanding_primary_km = Column(Float, nullable=True)
    dist_nearest_outstanding_secondary_km = Column(Float, nullable=True)
    primary_schools_within_2km = Column(Integer, nullable=True)
    secondary_schools_within_3km = Column(Integer, nullable=True)
    # Healthcare (NHS) — populated via /enrich/healthcare endpoint
    dist_nearest_gp_km = Column(Float, nullable=True)
    nearest_gp_name = Column(String, nullable=True)
    dist_nearest_hospital_km = Column(Float, nullable=True)
    nearest_hospital_name = Column(String, nullable=True)
    gp_practices_within_2km = Column(Integer, nullable=True)
    # Supermarkets (Geolytix) — populated via /enrich/supermarkets endpoint
    dist_nearest_supermarket_km = Column(Float, nullable=True)
    nearest_supermarket_name = Column(String, nullable=True)
    nearest_supermarket_brand = Column(String, nullable=True)
    dist_nearest_premium_supermarket_km = Column(Float, nullable=True)  # Waitrose/M&S
    dist_nearest_budget_supermarket_km = Column(Float, nullable=True)  # Aldi/Lidl
    supermarkets_within_2km = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_property_postcode_created", "postcode", "created_at"),
        Index("ix_property_type_bedrooms", "property_type", "bedrooms"),
    )

    sales = relationship("Sale", back_populates="property", cascade="all, delete-orphan")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    date_sold = Column(String)
    price = Column(String)
    price_numeric = Column(Integer, nullable=True, index=True)
    date_sold_iso = Column(String, nullable=True, index=True)
    price_change_pct = Column(String)
    property_type = Column(String)
    tenure = Column(String)

    property = relationship("Property", back_populates="sales")

    __table_args__ = (
        UniqueConstraint("property_id", "date_sold", "price", name="uq_sale"),
        Index("ix_sale_property_date", "property_id", "date_sold_iso"),
        Index("ix_sale_property_price", "property_id", "price_numeric"),
        Index("ix_sale_date_price", "date_sold_iso", "price_numeric"),
    )


class PlanningApplication(Base):
    __tablename__ = "planning_applications"

    id = Column(Integer, primary_key=True, index=True)
    postcode = Column(String, nullable=False, index=True)
    reference = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=True)  # pending/decided
    decision_date = Column(String, nullable=True)
    application_type = Column(String, nullable=True)  # full/outline/householder/etc
    is_major = Column(Integer, default=0)  # 0/1 boolean
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("postcode", "reference", name="uq_planning_app"),
        Index("ix_planning_postcode_fetched", "postcode", "fetched_at"),
    )


class CrimeStats(Base):
    __tablename__ = "crime_stats"

    id = Column(Integer, primary_key=True, index=True)
    postcode = Column(String, nullable=False, index=True)
    month = Column(String, nullable=False)  # YYYY-MM
    category = Column(String, nullable=False)
    count = Column(Integer, default=0)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("postcode", "month", "category", name="uq_crime_stat"),
        Index("ix_crime_category_postcode", "category", "postcode"),
        Index("ix_crime_postcode_fetched", "postcode", "fetched_at"),
    )
