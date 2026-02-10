from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

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
    from .parsing import parse_price_to_int, parse_date_to_iso
    import sqlalchemy

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
