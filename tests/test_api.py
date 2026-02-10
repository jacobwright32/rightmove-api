"""Integration tests for the FastAPI endpoints."""

import pytest

from app.models import Property, Sale


class TestRootEndpoint:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["docs"] == "/docs"


class TestPropertiesEndpoints:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/properties")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client, db_session):
        prop = Property(address="10 High Street, SW20 8NE", postcode="SW20 8NE")
        db_session.add(prop)
        db_session.commit()

        resp = client.get("/api/v1/properties")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["address"] == "10 High Street, SW20 8NE"

    def test_filter_by_postcode(self, client, db_session):
        db_session.add(Property(address="10 High St, SW20 8NE", postcode="SW20 8NE"))
        db_session.add(Property(address="5 Low St, E1 6AA", postcode="E1 6AA"))
        db_session.commit()

        resp = client.get("/api/v1/properties?postcode=SW20")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["postcode"] == "SW20 8NE"

    def test_get_property_not_found(self, client):
        resp = client.get("/api/v1/properties/999")
        assert resp.status_code == 404

    def test_get_property_with_sales(self, client, db_session):
        prop = Property(address="10 High Street, SW20 8NE", postcode="SW20 8NE")
        db_session.add(prop)
        db_session.flush()
        sale = Sale(
            property_id=prop.id,
            date_sold="4 Nov 2023",
            price="£450,000",
            price_numeric=450000,
            date_sold_iso="2023-11-04",
        )
        db_session.add(sale)
        db_session.commit()

        resp = client.get(f"/api/v1/properties/{prop.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["address"] == "10 High Street, SW20 8NE"
        assert len(data["sales"]) == 1
        assert data["sales"][0]["price_numeric"] == 450000


class TestPostcodesEndpoint:
    def test_list_postcodes_empty(self, client):
        resp = client.get("/api/v1/postcodes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_postcodes(self, client, db_session):
        db_session.add(Property(address="10 High St, SW20 8NE", postcode="SW20 8NE"))
        db_session.add(Property(address="11 High St, SW20 8NE", postcode="SW20 8NE"))
        db_session.add(Property(address="5 Low St, E1 6AA", postcode="E1 6AA"))
        db_session.commit()

        resp = client.get("/api/v1/postcodes")
        data = resp.json()
        assert len(data) == 2
        postcodes = {d["postcode"] for d in data}
        assert postcodes == {"SW20 8NE", "E1 6AA"}


class TestMarketOverview:
    def test_empty_db(self, client):
        resp = client.get("/api/v1/analytics/market-overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_properties"] == 0
        assert data["total_sales"] == 0
        assert data["total_postcodes"] == 0

    def test_with_data(self, client, db_session):
        prop = Property(address="10 High St, SW20 8NE", postcode="SW20 8NE", bedrooms=3)
        db_session.add(prop)
        db_session.flush()
        db_session.add(Sale(
            property_id=prop.id,
            date_sold="4 Nov 2023",
            price="£450,000",
            price_numeric=450000,
            date_sold_iso="2023-11-04",
        ))
        db_session.commit()

        resp = client.get("/api/v1/analytics/market-overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_properties"] == 1
        assert data["total_sales"] == 1
        assert data["total_postcodes"] == 1
        assert data["avg_price"] == 450000
        assert data["median_price"] == 450000
        assert len(data["price_distribution"]) == 5
        assert len(data["top_postcodes"]) == 1
        assert data["top_postcodes"][0]["postcode"] == "SW20 8NE"


class TestSimilarProperties:
    def test_not_found(self, client):
        resp = client.get("/api/v1/properties/999/similar")
        assert resp.status_code == 404

    def test_with_similar(self, client, db_session):
        # Target property
        target = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            property_type="Semi-detached", bedrooms=3,
        )
        db_session.add(target)
        db_session.flush()
        db_session.add(Sale(
            property_id=target.id, price_numeric=450000,
            date_sold_iso="2023-11-04", date_sold="4 Nov 2023", price="£450,000",
        ))

        # Similar property (same outcode, type, beds)
        similar = Property(
            address="12 High St, SW20 8NE", postcode="SW20 8NE",
            property_type="Semi-detached", bedrooms=3,
        )
        db_session.add(similar)
        db_session.flush()
        db_session.add(Sale(
            property_id=similar.id, price_numeric=460000,
            date_sold_iso="2023-10-01", date_sold="1 Oct 2023", price="£460,000",
        ))

        # Different area property (should not appear)
        other = Property(
            address="5 Low St, E1 6AA", postcode="E1 6AA",
            property_type="Semi-detached", bedrooms=3,
        )
        db_session.add(other)
        db_session.flush()
        db_session.add(Sale(
            property_id=other.id, price_numeric=300000,
            date_sold_iso="2023-09-01", date_sold="1 Sep 2023", price="£300,000",
        ))
        db_session.commit()

        resp = client.get(f"/api/v1/properties/{target.id}/similar")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["address"] == "12 High St, SW20 8NE"


class TestScrapePropertyValidation:
    def test_invalid_url(self, client):
        resp = client.post("/api/v1/scrape/property", json={"url": "https://example.com"})
        assert resp.status_code == 400
        assert "Rightmove" in resp.json()["detail"]
