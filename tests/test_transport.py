"""Tests for transport distance enrichment."""

import numpy as np

from app.enrichment.transport import (
    UK_AIRPORTS,
    UK_PORTS,
    _build_cartesian,
    _haversine_km,
    _point_to_cartesian,
    compute_transport_distances,
)
from app.models import Property

# ── Haversine tests ──────────────────────────────────────────────


class TestHaversine:
    def test_same_point_zero(self):
        assert _haversine_km(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_london_to_manchester(self):
        dist = _haversine_km(51.5074, -0.1278, 53.4808, -2.2426)
        assert 255 < dist < 270

    def test_symmetric(self):
        d1 = _haversine_km(51.5, -0.1, 52.0, -1.0)
        d2 = _haversine_km(52.0, -1.0, 51.5, -0.1)
        assert abs(d1 - d2) < 0.001


# ── Cartesian conversion tests ──────────────────────────────────


class TestCartesian:
    def test_unit_sphere(self):
        lats = np.radians(np.array([51.5, 53.4, 55.0]))
        lons = np.radians(np.array([-0.1, -2.2, -3.5]))
        cart = _build_cartesian(lats, lons)
        for row in cart:
            assert abs(np.linalg.norm(row) - 1.0) < 1e-10

    def test_single_point_unit_sphere(self):
        pt = _point_to_cartesian(51.5, -0.1)
        assert abs(np.linalg.norm(pt) - 1.0) < 1e-10


# ── Static data validation ───────────────────────────────────────


class TestStaticData:
    def test_airports_have_valid_coords(self):
        for a in UK_AIRPORTS:
            assert "name" in a and "lat" in a and "lon" in a
            assert 49 < a["lat"] < 61, f"{a['name']} lat out of UK range"
            assert -8 < a["lon"] < 3, f"{a['name']} lon out of UK range"

    def test_ports_have_valid_coords(self):
        for p in UK_PORTS:
            assert "name" in p and "lat" in p and "lon" in p
            assert 49 < p["lat"] < 61, f"{p['name']} lat out of UK range"
            assert -8 < p["lon"] < 3, f"{p['name']} lon out of UK range"

    def test_no_duplicate_airport_names(self):
        names = [a["name"] for a in UK_AIRPORTS]
        assert len(names) == len(set(names))

    def test_no_duplicate_port_names(self):
        names = [p["name"] for p in UK_PORTS]
        assert len(names) == len(set(names))


# ── compute_transport_distances tests ────────────────────────────


class TestComputeDistances:
    def test_returns_none_when_trees_unavailable(self, monkeypatch):
        import app.enrichment.transport as mod
        monkeypatch.setattr(mod, "_initialized", False)
        monkeypatch.setattr(mod, "_trees", {})
        monkeypatch.setattr(mod, "_airport_tree", None)
        monkeypatch.setattr(mod, "_port_tree", None)
        monkeypatch.setattr(mod, "_ensure_naptan_data", lambda: None)

        result = compute_transport_distances(51.5, -0.1)
        assert result is None

        # Reset so other tests aren't affected
        monkeypatch.setattr(mod, "_initialized", False)


# ── API endpoint tests ───────────────────────────────────────────


class TestTransportEndpoint:
    def test_no_properties_404(self, client):
        resp = client.post("/api/v1/enrich/transport/XX99 9XX")
        assert resp.status_code == 404

    def test_enriches_with_mocked_naptan(self, client, db_session, monkeypatch):
        """Seed a property, mock NaPTAN, verify enrichment works."""
        import pandas as pd

        import app.enrichment.transport as mod

        # Seed property
        prop = Property(
            address="10 Test St, SW20 8NE",
            postcode="SW20 8NE",
            latitude=51.42,
            longitude=-0.21,
        )
        db_session.add(prop)
        db_session.commit()

        # Reset singleton state
        monkeypatch.setattr(mod, "_initialized", False)
        monkeypatch.setattr(mod, "_trees", {})
        monkeypatch.setattr(mod, "_airport_tree", None)
        monkeypatch.setattr(mod, "_port_tree", None)

        # Mock NaPTAN to return a small DataFrame
        mock_df = pd.DataFrame({
            "ATCOCode": ["9100WMBL", "9400ZZLUBNK", "490000123"],
            "CommonName": ["Wimbledon", "Bank", "Bus Stop A"],
            "Latitude": [51.4213, 51.5133, 51.42],
            "Longitude": [-0.2064, -0.0886, -0.21],
            "StopType": ["RSE", "TMU", "BCT"],
        })
        monkeypatch.setattr(mod, "_ensure_naptan_data", lambda: mock_df)

        resp = client.post("/api/v1/enrich/transport/SW20%208NE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["properties_updated"] == 1
        assert "Updated 1" in data["message"]

        # Verify values were stored
        db_session.refresh(prop)
        assert prop.dist_nearest_rail_km is not None
        assert prop.nearest_rail_station == "Wimbledon"
        assert prop.dist_nearest_airport_km is not None
        assert prop.nearest_airport is not None
        assert prop.bus_stops_within_500m is not None

        # Reset
        monkeypatch.setattr(mod, "_initialized", False)


# ── Modelling feature registry tests ─────────────────────────────


class TestTransportFeatures:
    def test_transport_features_in_registry(self):
        from app.modelling.data_assembly import FEATURE_REGISTRY

        transport_features = [
            f for f in FEATURE_REGISTRY if f["category"] == "Transport"
        ]
        names = {f["name"] for f in transport_features}
        assert "dist_nearest_rail_km" in names
        assert "dist_nearest_tube_km" in names
        assert "dist_nearest_bus_km" in names
        assert "dist_nearest_airport_km" in names
        assert "dist_nearest_port_km" in names
        assert "bus_stops_within_500m" in names
        assert "nearest_rail_station" in names
        assert "nearest_tube_station" in names
        assert "nearest_airport" in names
        assert "nearest_port" in names
        assert "dist_nearest_tram_km" not in names
        assert len(transport_features) == 10

    def test_station_names_are_categorical(self):
        from app.modelling.data_assembly import _CATEGORICAL_FEATURES

        assert "nearest_rail_station" in _CATEGORICAL_FEATURES
        assert "nearest_tube_station" in _CATEGORICAL_FEATURES
        assert "nearest_airport" in _CATEGORICAL_FEATURES
        assert "nearest_port" in _CATEGORICAL_FEATURES
