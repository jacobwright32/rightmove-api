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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
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
    )
