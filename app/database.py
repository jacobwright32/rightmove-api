from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _migrate_db():
    """Add columns that may be missing from existing databases."""
    import sqlalchemy
    with engine.connect() as conn:
        migrations = [
            "ALTER TABLE properties ADD COLUMN floorplan_urls TEXT",
            "ALTER TABLE sales ADD COLUMN price_numeric INTEGER",
            "ALTER TABLE sales ADD COLUMN date_sold_iso TEXT",
            "ALTER TABLE properties ADD COLUMN epc_rating TEXT",
            "ALTER TABLE properties ADD COLUMN epc_score INTEGER",
            "ALTER TABLE properties ADD COLUMN epc_environment_impact INTEGER",
            "ALTER TABLE properties ADD COLUMN estimated_energy_cost INTEGER",
            "ALTER TABLE properties ADD COLUMN flood_risk_level TEXT",
            "ALTER TABLE properties ADD COLUMN latitude REAL",
            "ALTER TABLE properties ADD COLUMN longitude REAL",
            "ALTER TABLE properties ADD COLUMN listing_status TEXT",
            "ALTER TABLE properties ADD COLUMN listing_price INTEGER",
            "ALTER TABLE properties ADD COLUMN listing_price_display TEXT",
            "ALTER TABLE properties ADD COLUMN listing_date TEXT",
            "ALTER TABLE properties ADD COLUMN listing_url TEXT",
            "ALTER TABLE properties ADD COLUMN listing_checked_at TIMESTAMP",
            "ALTER TABLE properties ADD COLUMN dist_nearest_rail_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_tube_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_tram_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_bus_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_airport_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_port_km REAL",
            "ALTER TABLE properties ADD COLUMN nearest_rail_station TEXT",
            "ALTER TABLE properties ADD COLUMN nearest_tube_station TEXT",
            "ALTER TABLE properties ADD COLUMN nearest_airport TEXT",
            "ALTER TABLE properties ADD COLUMN nearest_port TEXT",
            "ALTER TABLE properties ADD COLUMN bus_stops_within_500m INTEGER",
            # IMD deprivation
            "ALTER TABLE properties ADD COLUMN imd_decile INTEGER",
            "ALTER TABLE properties ADD COLUMN imd_income_decile INTEGER",
            "ALTER TABLE properties ADD COLUMN imd_employment_decile INTEGER",
            "ALTER TABLE properties ADD COLUMN imd_education_decile INTEGER",
            "ALTER TABLE properties ADD COLUMN imd_health_decile INTEGER",
            "ALTER TABLE properties ADD COLUMN imd_crime_decile INTEGER",
            "ALTER TABLE properties ADD COLUMN imd_housing_decile INTEGER",
            "ALTER TABLE properties ADD COLUMN imd_environment_decile INTEGER",
            # Broadband
            "ALTER TABLE properties ADD COLUMN broadband_median_speed REAL",
            "ALTER TABLE properties ADD COLUMN broadband_superfast_pct REAL",
            "ALTER TABLE properties ADD COLUMN broadband_ultrafast_pct REAL",
            "ALTER TABLE properties ADD COLUMN broadband_full_fibre_pct REAL",
            # Schools
            "ALTER TABLE properties ADD COLUMN dist_nearest_primary_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_secondary_km REAL",
            "ALTER TABLE properties ADD COLUMN nearest_primary_school TEXT",
            "ALTER TABLE properties ADD COLUMN nearest_secondary_school TEXT",
            "ALTER TABLE properties ADD COLUMN nearest_primary_ofsted TEXT",
            "ALTER TABLE properties ADD COLUMN nearest_secondary_ofsted TEXT",
            "ALTER TABLE properties ADD COLUMN dist_nearest_outstanding_primary_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_outstanding_secondary_km REAL",
            "ALTER TABLE properties ADD COLUMN primary_schools_within_2km INTEGER",
            "ALTER TABLE properties ADD COLUMN secondary_schools_within_3km INTEGER",
            # Healthcare
            "ALTER TABLE properties ADD COLUMN dist_nearest_gp_km REAL",
            "ALTER TABLE properties ADD COLUMN nearest_gp_name TEXT",
            "ALTER TABLE properties ADD COLUMN dist_nearest_hospital_km REAL",
            "ALTER TABLE properties ADD COLUMN nearest_hospital_name TEXT",
            "ALTER TABLE properties ADD COLUMN gp_practices_within_2km INTEGER",
            # Supermarkets
            "ALTER TABLE properties ADD COLUMN dist_nearest_supermarket_km REAL",
            "ALTER TABLE properties ADD COLUMN nearest_supermarket_name TEXT",
            "ALTER TABLE properties ADD COLUMN nearest_supermarket_brand TEXT",
            "ALTER TABLE properties ADD COLUMN dist_nearest_premium_supermarket_km REAL",
            "ALTER TABLE properties ADD COLUMN dist_nearest_budget_supermarket_km REAL",
            "ALTER TABLE properties ADD COLUMN supermarkets_within_2km INTEGER",
        ]
        for sql in migrations:
            try:
                conn.execute(sqlalchemy.text(sql))
                conn.commit()
            except Exception:
                conn.rollback()

    _backfill_parsed_fields()


def _backfill_parsed_fields():
    """Parse existing price/date strings into the new numeric/ISO columns."""
    import sqlalchemy
    from sqlalchemy import inspect as sa_inspect

    from .parsing import parse_date_to_iso, parse_price_to_int

    # Skip if the sales table doesn't exist yet (fresh DB)
    if not sa_inspect(engine).has_table("sales"):
        return

    with engine.connect() as conn:
        rows = conn.execute(sqlalchemy.text(
            "SELECT id, price, date_sold FROM sales "
            "WHERE (price_numeric IS NULL AND price IS NOT NULL) "
            "   OR (date_sold_iso IS NULL AND date_sold IS NOT NULL)"
        )).fetchall()

        for row in rows:
            price_numeric = parse_price_to_int(row[1]) if row[1] else None
            date_iso = parse_date_to_iso(row[2]) if row[2] else None
            conn.execute(
                sqlalchemy.text(
                    "UPDATE sales SET price_numeric = :price, date_sold_iso = :date "
                    "WHERE id = :id"
                ),
                {"price": price_numeric, "date": date_iso, "id": row[0]},
            )
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
