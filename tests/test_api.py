"""Integration tests for the FastAPI endpoints."""


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


class TestHousingInsights:
    def test_empty_db(self, client):
        resp = client.get("/api/v1/analytics/housing-insights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 0
        assert data["kpis"]["total_properties"] == 0
        assert data["price_histogram"] == []
        assert data["time_series"] == []
        assert data["scatter_data"] == []
        assert data["postcode_heatmap"] == []
        assert data["investment_deals"] == []

    def test_with_data(self, client, db_session):
        prop1 = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            property_type="Semi-detached", bedrooms=3,
        )
        prop2 = Property(
            address="20 Low St, SW20 8NE", postcode="SW20 8NE",
            property_type="Terraced", bedrooms=2,
        )
        db_session.add_all([prop1, prop2])
        db_session.flush()
        db_session.add(Sale(
            property_id=prop1.id, price_numeric=450000,
            date_sold_iso="2023-11-04", date_sold="4 Nov 2023", price="£450,000",
        ))
        db_session.add(Sale(
            property_id=prop2.id, price_numeric=300000,
            date_sold_iso="2023-10-01", date_sold="1 Oct 2023", price="£300,000",
        ))
        db_session.commit()

        resp = client.get("/api/v1/analytics/housing-insights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 2
        assert data["kpis"]["total_properties"] == 2
        assert data["kpis"]["median_price"] == 375000
        assert len(data["price_histogram"]) > 0
        assert len(data["time_series"]) > 0
        assert len(data["scatter_data"]) == 2
        assert len(data["postcode_heatmap"]) > 0

    def test_filters(self, client, db_session):
        prop1 = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            property_type="Semi-detached", bedrooms=3,
        )
        prop2 = Property(
            address="5 Low St, E1 6AA", postcode="E1 6AA",
            property_type="Flat", bedrooms=1,
        )
        db_session.add_all([prop1, prop2])
        db_session.flush()
        db_session.add(Sale(
            property_id=prop1.id, price_numeric=450000,
            date_sold_iso="2023-11-04", date_sold="4 Nov 2023", price="£450,000",
        ))
        db_session.add(Sale(
            property_id=prop2.id, price_numeric=200000,
            date_sold_iso="2023-10-01", date_sold="1 Oct 2023", price="£200,000",
        ))
        db_session.commit()

        # Filter by postcode prefix
        resp = client.get("/api/v1/analytics/housing-insights?postcode_prefix=SW20")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 1
        assert data["kpis"]["total_properties"] == 1

        # Filter by property type
        resp = client.get("/api/v1/analytics/housing-insights?property_type=FLAT")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 1

        # Filter by min bedrooms
        resp = client.get("/api/v1/analytics/housing-insights?min_bedrooms=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 1


class TestSkipExistingScrape:
    """Tests for the skip-already-scraped feature."""

    def test_fresh_postcode_is_skipped(self, client, db_session):
        """If postcode has fresh data, scrape should be skipped by default."""
        from datetime import datetime, timezone

        prop = Property(
            address="10 High St, SW20 8NE",
            postcode="SW20 8NE",
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(prop)
        db_session.commit()

        from app.routers.scraper import _is_postcode_fresh

        is_fresh, count = _is_postcode_fresh(db_session, "SW20 8NE")
        assert is_fresh is True
        assert count == 1

    def test_stale_postcode_is_not_fresh(self, client, db_session):
        """If postcode data is older than freshness window, it should not be considered fresh."""
        from datetime import datetime, timedelta, timezone

        stale_time = datetime.now(timezone.utc) - timedelta(days=30)
        prop = Property(
            address="10 High St, SW20 8NE",
            postcode="SW20 8NE",
            updated_at=stale_time,
        )
        db_session.add(prop)
        db_session.commit()

        from app.routers.scraper import _is_postcode_fresh

        is_fresh, count = _is_postcode_fresh(db_session, "SW20 8NE")
        assert is_fresh is False
        assert count == 1

    def test_unknown_postcode_is_not_fresh(self, client, db_session):
        """If postcode has no data at all, it should not be considered fresh."""
        from app.routers.scraper import _is_postcode_fresh

        is_fresh, count = _is_postcode_fresh(db_session, "E1 6AA")
        assert is_fresh is False
        assert count == 0

    def test_scrape_response_includes_skipped_field(self, client, db_session):
        """ScrapeResponse schema should include the skipped field."""
        from app.schemas import ScrapeResponse

        resp = ScrapeResponse(
            message="test", properties_scraped=0, skipped=True,
        )
        assert resp.skipped is True

        resp2 = ScrapeResponse(
            message="test", properties_scraped=5,
        )
        assert resp2.skipped is False

    def test_area_response_includes_skipped_postcodes(self, client, db_session):
        """AreaScrapeResponse schema should include postcodes_skipped."""
        from app.schemas import AreaScrapeResponse

        resp = AreaScrapeResponse(
            message="test",
            postcodes_scraped=["SW20 8NE"],
            postcodes_skipped=["SW20 8ND"],
            total_properties=5,
        )
        assert resp.postcodes_skipped == ["SW20 8ND"]


class TestEPCEnrichment:
    """Tests for EPC enrichment feature."""

    def test_epc_no_properties(self, client, db_session):
        """EPC enrichment should 404 if no properties exist for postcode."""
        resp = client.post("/api/v1/enrich/epc/XX1 1XX")
        assert resp.status_code == 404

    def test_epc_properties_without_credentials(self, client, db_session):
        """EPC enrichment without API creds should return 0 updated."""
        db_session.add(Property(address="10 High St, SW20 8NE", postcode="SW20 8NE"))
        db_session.commit()

        resp = client.post("/api/v1/enrich/epc/SW20 8NE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["properties_updated"] == 0
        assert data["certificates_found"] == 0

    def test_epc_fields_on_property(self, client, db_session):
        """Property response should include EPC fields."""
        prop = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            epc_rating="C", epc_score=72, epc_environment_impact=65,
            estimated_energy_cost=1200,
        )
        db_session.add(prop)
        db_session.commit()

        resp = client.get(f"/api/v1/properties/{prop.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["epc_rating"] == "C"
        assert data["epc_score"] == 72
        assert data["epc_environment_impact"] == 65
        assert data["estimated_energy_cost"] == 1200


class TestCrimeEndpoint:
    """Tests for crime data endpoint."""

    def test_crime_endpoint_exists(self, client):
        """Crime endpoint should exist and return valid response."""
        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/crime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["postcode"] == "SW20 8NE"
        assert "categories" in data
        assert "monthly_trend" in data
        assert "total_crimes" in data

    def test_crime_empty_result(self, client):
        """Crime endpoint should handle postcodes with no data gracefully."""
        resp = client.get("/api/v1/analytics/postcode/XX1 1XX/crime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_crimes"] == 0
        assert data["categories"] == {}

    def test_crime_cached_data(self, client, db_session):
        """Crime stats should be servable from cache."""
        from datetime import datetime, timezone

        from app.models import CrimeStats

        db_session.add(CrimeStats(
            postcode="SW20 8NE", month="2025-12",
            category="burglary", count=5,
            fetched_at=datetime.now(timezone.utc),
        ))
        db_session.add(CrimeStats(
            postcode="SW20 8NE", month="2025-12",
            category="anti-social-behaviour", count=12,
            fetched_at=datetime.now(timezone.utc),
        ))
        db_session.commit()

        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/crime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cached"] is True
        assert data["total_crimes"] == 17
        assert data["categories"]["anti-social-behaviour"] == 12
        assert data["categories"]["burglary"] == 5


class TestPropertiesGeo:
    """Tests for map view geo endpoint."""

    def test_geo_empty_db(self, client):
        """Geo endpoint should return empty list with no data."""
        resp = client.get("/api/v1/properties/geo")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_geo_with_properties(self, client, db_session):
        """Geo endpoint should return properties with coordinates."""
        prop = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            latitude=51.4, longitude=-0.2, property_type="Terraced",
            bedrooms=3,
        )
        db_session.add(prop)
        db_session.flush()
        db_session.add(Sale(
            property_id=prop.id, price_numeric=450000,
            date_sold_iso="2023-11-04", date_sold="4 Nov 2023",
            price="£450,000",
        ))
        db_session.commit()

        resp = client.get("/api/v1/properties/geo")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["latitude"] == 51.4
        assert data[0]["longitude"] == -0.2
        assert data[0]["latest_price"] == 450000
        assert data[0]["postcode"] == "SW20 8NE"

    def test_geo_schema_fields(self, client, db_session):
        """Geo response should include all expected fields."""
        prop = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            latitude=51.4, longitude=-0.2, epc_rating="C",
            flood_risk_level="low",
        )
        db_session.add(prop)
        db_session.commit()

        resp = client.get("/api/v1/properties/geo")
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        assert "id" in item
        assert "address" in item
        assert "latitude" in item
        assert "longitude" in item
        assert item["epc_rating"] == "C"
        assert item["flood_risk_level"] == "low"


class TestFloodRisk:
    """Tests for flood risk assessment endpoint."""

    def test_flood_endpoint_exists(self, client):
        """Flood risk endpoint should exist and return valid response."""
        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/flood-risk")
        assert resp.status_code == 200
        data = resp.json()
        assert data["postcode"] == "SW20 8NE"
        assert "risk_level" in data
        assert data["risk_level"] in ("very_low", "low", "medium", "high", "unknown")
        assert "active_warnings" in data

    def test_flood_risk_cached_on_property(self, client, db_session):
        """Flood risk level should be cached on property after assessment."""
        prop = Property(address="10 High St, SW20 8NE", postcode="SW20 8NE")
        db_session.add(prop)
        db_session.commit()

        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/flood-risk")
        assert resp.status_code == 200

        # Refresh property from DB
        db_session.refresh(prop)
        # If geocoding succeeded, risk_level should be cached
        if resp.json()["risk_level"] != "unknown":
            assert prop.flood_risk_level is not None

    def test_flood_risk_on_property_response(self, client, db_session):
        """Property response should include flood_risk_level field."""
        prop = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            flood_risk_level="low",
        )
        db_session.add(prop)
        db_session.commit()

        resp = client.get(f"/api/v1/properties/{prop.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["flood_risk_level"] == "low"


class TestCapitalGrowth:
    """Tests for capital growth & forecasting endpoints."""

    def test_growth_empty_db(self, client):
        """Growth endpoint should 404 with no data."""
        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/growth")
        assert resp.status_code == 404

    def test_growth_with_multiyear_data(self, client, db_session):
        """Growth endpoint should return CAGR when multi-year data exists."""
        prop = Property(address="10 High St, SW20 8NE", postcode="SW20 8NE")
        db_session.add(prop)
        db_session.flush()
        # Add sales spanning 3 years
        for year, price in [(2020, 300000), (2021, 330000), (2022, 360000), (2023, 400000)]:
            db_session.add(Sale(
                property_id=prop.id, price_numeric=price,
                date_sold_iso=f"{year}-06-15", date_sold=f"15 Jun {year}",
                price=f"£{price:,}",
            ))
        db_session.commit()

        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/growth")
        assert resp.status_code == 200
        data = resp.json()
        assert data["postcode"] == "SW20 8NE"
        assert data["data_years"] == 3
        assert len(data["annual_medians"]) == 4
        assert len(data["metrics"]) == 4  # 1,3,5,10 year periods
        # 3-year CAGR should be calculable
        three_yr = next((m for m in data["metrics"] if m["period_years"] == 3), None)
        assert three_yr is not None
        assert three_yr["cagr_pct"] is not None
        assert three_yr["cagr_pct"] > 0  # prices went up

    def test_growth_insufficient_data(self, client, db_session):
        """Growth with only 1 year should return 0 data_years and no volatility."""
        prop = Property(address="10 High St, SW20 8NE", postcode="SW20 8NE")
        db_session.add(prop)
        db_session.flush()
        db_session.add(Sale(
            property_id=prop.id, price_numeric=300000,
            date_sold_iso="2023-06-15", date_sold="15 Jun 2023",
            price="£300,000",
        ))
        db_session.commit()

        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/growth")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_years"] == 0
        assert data["volatility_pct"] is None
        assert data["max_drawdown_pct"] is None

    def test_growth_leaderboard(self, client, db_session):
        """Growth leaderboard should return postcodes sorted by CAGR."""
        for pc_suffix, prices in [("8NE", [200000, 300000]), ("8ND", [200000, 220000])]:
            prop = Property(address=f"10 High St, SW20 {pc_suffix}", postcode=f"SW20 {pc_suffix}")
            db_session.add(prop)
            db_session.flush()
            for i, price in enumerate(prices):
                db_session.add(Sale(
                    property_id=prop.id, price_numeric=price,
                    date_sold_iso=f"{2020 + i * 3}-06-15",
                    date_sold=f"15 Jun {2020 + i * 3}",
                    price=f"£{price:,}",
                ))
        db_session.commit()

        resp = client.get("/api/v1/analytics/growth-leaderboard?period=3&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # SW20 8NE had bigger growth (200k->300k = 50%) vs 8ND (200k->220k = 10%)
        assert data[0]["postcode"] == "SW20 8NE"
        assert data[0]["cagr_pct"] > data[1]["cagr_pct"]


class TestScrapePropertyValidation:
    def test_invalid_url(self, client):
        resp = client.post("/api/v1/scrape/property", json={"url": "https://example.com"})
        assert resp.status_code == 400
        assert "Rightmove" in resp.json()["detail"]
