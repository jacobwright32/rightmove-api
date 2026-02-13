"""Integration tests for the FastAPI endpoints."""


from app.models import PlanningApplication, Property, Sale


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


    def test_listing_only_filter(self, client, db_session):
        """listing_only=true returns only for-sale listings, false returns only properties with sales."""
        # Property with sale history (house prices data)
        sale_prop = Property(address="1 Sale Rd, SW20 8NE", postcode="SW20 8NE")
        db_session.add(sale_prop)
        db_session.flush()
        db_session.add(Sale(property_id=sale_prop.id, date_sold="1 Jan 2024", price="£300,000", price_numeric=300000, date_sold_iso="2024-01-01"))

        # Property with listing status (for-sale data)
        listing_prop = Property(address="2 Listing Ave, SW20 8NE", postcode="SW20 8NE", listing_status="for_sale", listing_price=400000)
        db_session.add(listing_prop)
        db_session.commit()

        # listing_only=true -> only the listing property
        resp = client.get("/api/v1/properties?postcode=SW20&listing_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["address"] == "2 Listing Ave, SW20 8NE"

        # listing_only=false -> only the property with sales
        resp = client.get("/api/v1/properties?postcode=SW20&listing_only=false")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["address"] == "1 Sale Rd, SW20 8NE"

        # No filter -> both
        resp = client.get("/api/v1/properties?postcode=SW20")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


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


    def test_has_listing_filter(self, client, db_session):
        """has_listing=true returns only properties with listing_status AND sales."""
        # Property with sales only
        p1 = Property(address="1 Sale St, SW20 8NE", postcode="SW20 8NE", bedrooms=2)
        db_session.add(p1)
        db_session.flush()
        db_session.add(Sale(property_id=p1.id, date_sold="1 Jan 2024", price="£300,000", price_numeric=300000, date_sold_iso="2024-01-01"))

        # Property with sales AND listing
        p2 = Property(address="2 Both Ave, SW20 8NE", postcode="SW20 8NE", bedrooms=3, listing_status="for_sale", listing_price=400000)
        db_session.add(p2)
        db_session.flush()
        db_session.add(Sale(property_id=p2.id, date_sold="1 Jun 2023", price="£350,000", price_numeric=350000, date_sold_iso="2023-06-01"))

        # Property with listing only (no sales) — won't appear in any housing insights (inner join)
        p3 = Property(address="3 Listing Rd, SW20 8NE", postcode="SW20 8NE", listing_status="for_sale", listing_price=500000)
        db_session.add(p3)
        db_session.commit()

        # has_listing=true: only p2
        resp = client.get("/api/v1/analytics/housing-insights?has_listing=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 1

        # has_listing=false: only p1
        resp = client.get("/api/v1/analytics/housing-insights?has_listing=false")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 1

        # No filter: both p1 and p2 (p3 excluded by inner join)
        resp = client.get("/api/v1/analytics/housing-insights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpis"]["total_sales"] == 2


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

    def test_epc_enrichment_with_properties(self, client, db_session):
        """EPC enrichment endpoint returns valid response shape."""
        db_session.add(Property(address="10 High St, SW20 8NE", postcode="SW20 8NE"))
        db_session.commit()

        resp = client.post("/api/v1/enrich/epc/SW20 8NE")
        assert resp.status_code == 200
        data = resp.json()
        # Response should always have these fields regardless of creds/API result
        assert "message" in data
        assert "properties_updated" in data
        assert "certificates_found" in data
        assert isinstance(data["properties_updated"], int)
        assert isinstance(data["certificates_found"], int)

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


class TestPlanningApplications:
    def test_planning_endpoint_exists(self, client):
        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/planning")
        assert resp.status_code == 200
        data = resp.json()
        assert data["postcode"] == "SW20 8NE"
        assert "applications" in data
        assert "total_count" in data
        assert "major_count" in data

    def test_planning_cached_data(self, client, db_session):
        """Cached planning applications are returned without API call."""
        from datetime import datetime, timezone

        app = PlanningApplication(
            postcode="SW20 8NE",
            reference="23/00001/FUL",
            description="Erection of single storey rear extension",
            status="decided",
            decision_date="2023-05-09",
            application_type="full",
            is_major=0,
            fetched_at=datetime.now(timezone.utc),
        )
        db_session.add(app)
        db_session.commit()

        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/planning")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cached"] is True
        assert data["total_count"] == 1
        assert data["applications"][0]["reference"] == "23/00001/FUL"

    def test_major_development_flagging(self, client, db_session):
        """Major development keyword detection works."""
        from datetime import datetime, timezone

        apps = [
            PlanningApplication(
                postcode="SW20 8NE",
                reference="23/00001/FUL",
                description="Erection of 15 dwellings with parking",
                status="pending",
                application_type="full",
                is_major=1,
                fetched_at=datetime.now(timezone.utc),
            ),
            PlanningApplication(
                postcode="SW20 8NE",
                reference="23/00002/HH",
                description="Single storey rear extension",
                status="decided",
                application_type="householder",
                is_major=0,
                fetched_at=datetime.now(timezone.utc),
            ),
        ]
        db_session.add_all(apps)
        db_session.commit()

        resp = client.get("/api/v1/analytics/postcode/SW20 8NE/planning")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert data["major_count"] == 1


class TestListingStatus:
    """Tests for listing status / currently-for-sale feature."""

    def test_listing_endpoint_not_found(self, client):
        """Listing endpoint returns 404 for non-existent property."""
        resp = client.get("/api/v1/properties/999/listing")
        assert resp.status_code == 404

    def test_listing_cached_data(self, client, db_session):
        """Property with fresh listing data returns cached result."""
        from datetime import datetime, timezone

        prop = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            listing_status="for_sale", listing_price=450000,
            listing_price_display="£450,000",
            listing_url="https://www.rightmove.co.uk/properties/12345",
            listing_date="16th January 2026",
            listing_checked_at=datetime.now(timezone.utc),
        )
        db_session.add(prop)
        db_session.commit()

        resp = client.get(f"/api/v1/properties/{prop.id}/listing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["listing_status"] == "for_sale"
        assert data["listing_price"] == 450000
        assert data["listing_price_display"] == "£450,000"
        assert data["stale"] is False

    def test_listing_fields_on_property_response(self, client, db_session):
        """Property detail response should include listing fields."""
        prop = Property(
            address="10 High St, SW20 8NE", postcode="SW20 8NE",
            listing_status="for_sale", listing_price=450000,
            listing_price_display="Guide Price £450,000",
        )
        db_session.add(prop)
        db_session.commit()

        resp = client.get(f"/api/v1/properties/{prop.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["listing_status"] == "for_sale"
        assert data["listing_price"] == 450000
        assert data["listing_price_display"] == "Guide Price £450,000"

    def test_listing_enrichment_no_properties(self, client):
        """Listing enrichment should 404 with no properties for postcode."""
        resp = client.post("/api/v1/enrich/listing/XX1 1XX")
        assert resp.status_code == 404


class TestScrapeMode:
    def test_invalid_mode_returns_400(self, client):
        resp = client.post("/api/v1/scrape/postcode/SW208NE?mode=invalid")
        assert resp.status_code == 400
        assert "Invalid mode" in resp.json()["detail"]

    def test_default_mode_is_house_prices(self, client, db_session):
        """ScrapeResponse schema should include mode field defaulting to house_prices."""
        from app.schemas import ScrapeResponse
        r = ScrapeResponse(message="test", properties_scraped=0)
        assert r.mode == "house_prices"

    def test_upsert_sets_listing_fields(self, client, db_session):
        """When PropertyData has asking_price, _upsert_property should set listing columns."""
        from app.routers.scraper import _upsert_property
        from app.scraper.scraper import PropertyData

        data = PropertyData(
            address="99 Test Lane, SW20 8NE",
            postcode="SW20 8NE",
            property_type="DETACHED",
            bedrooms=4,
            asking_price=550000,
            asking_price_display="\u00a3550,000",
            listing_id="67890",
            url="https://www.rightmove.co.uk/properties/67890",
        )
        prop = _upsert_property(db_session, data)
        db_session.commit()
        db_session.refresh(prop)

        assert prop.listing_status == "for_sale"
        assert prop.listing_price == 550000
        assert prop.listing_price_display == "\u00a3550,000"
        assert prop.listing_url == "https://www.rightmove.co.uk/properties/67890"
        assert prop.listing_checked_at is not None


class TestScrapePropertyValidation:
    def test_invalid_url(self, client):
        resp = client.post("/api/v1/scrape/property", json={"url": "https://example.com"})
        assert resp.status_code == 400
        assert "URL" in resp.json()["detail"]
