"""Tests for the modelling endpoints (train, predict, features)."""

import json

from app.models import CrimeStats, Property, Sale


def _seed_properties(db, count=35):
    """Insert properties with sales for training tests."""
    for i in range(count):
        prop = Property(
            address=f"{i + 1} Test Street, SW1A 1AA",
            postcode="SW1A 1AA",
            bedrooms=(i % 5) + 1,
            bathrooms=(i % 3) + 1,
            property_type=["Detached", "Semi-Detached", "Terraced", "Flat"][i % 4],
            latitude=51.5 + i * 0.001,
            longitude=-0.1 + i * 0.001,
            extra_features=json.dumps({"features": [f"Garden", f"{60 + i * 10} sq ft"]}),
        )
        db.add(prop)
        db.flush()

        sale = Sale(
            property_id=prop.id,
            date_sold=f"{(i % 28) + 1} Jan 2023",
            price=f"£{200000 + i * 10000:,}",
            price_numeric=200000 + i * 10000,
            date_sold_iso=f"2023-01-{(i % 28) + 1:02d}",
            tenure="Freehold" if i % 2 == 0 else "Leasehold",
        )
        db.add(sale)

    db.commit()


class TestGetFeatures:
    def test_returns_features_and_targets(self, client, db_session):
        _seed_properties(db_session, count=5)
        resp = client.get("/api/v1/model/features")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["features"]) > 0
        assert len(data["targets"]) == 3
        assert data["total_properties_with_sales"] == 5

        # Check feature structure
        feat = data["features"][0]
        assert "name" in feat
        assert "category" in feat
        assert "label" in feat
        assert "dtype" in feat

    def test_empty_db(self, client):
        resp = client.get("/api/v1/model/features")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_properties_with_sales"] == 0
        assert len(data["features"]) > 0


class TestTrainValidation:
    def test_invalid_target(self, client, db_session):
        resp = client.post("/api/v1/model/train", json={
            "target": "invalid_target",
            "features": ["bedrooms"],
            "model_type": "lightgbm",
        })
        assert resp.status_code == 400
        assert "Invalid target" in resp.json()["detail"]

    def test_invalid_model_type(self, client, db_session):
        resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": ["bedrooms"],
            "model_type": "random_forest",
        })
        assert resp.status_code == 400
        assert "Invalid model_type" in resp.json()["detail"]

    def test_no_features(self, client, db_session):
        resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": [],
            "model_type": "lightgbm",
        })
        assert resp.status_code == 400
        assert "feature" in resp.json()["detail"].lower()

    def test_insufficient_data(self, client, db_session):
        _seed_properties(db_session, count=5)
        resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": ["bedrooms", "bathrooms"],
            "model_type": "lightgbm",
        })
        assert resp.status_code == 400
        assert "Insufficient data" in resp.json()["detail"]


class TestTrainLightGBM:
    def test_train_random_split(self, client, db_session):
        _seed_properties(db_session, count=35)
        resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": ["bedrooms", "bathrooms", "latitude", "longitude"],
            "model_type": "lightgbm",
            "split_strategy": "random",
            "split_params": {"test_ratio": 0.2},
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "model_id" in data
        assert len(data["model_id"]) == 8
        assert data["train_size"] + data["test_size"] == 35

        # Metrics
        metrics = data["metrics"]
        assert "r_squared" in metrics
        assert "rmse" in metrics
        assert "mae" in metrics
        assert "mape" in metrics

        # Feature importances
        assert len(data["feature_importances"]) > 0
        assert data["feature_importances"][0]["feature"] in [
            "bedrooms", "bathrooms", "latitude", "longitude",
        ]

        # Predictions
        assert len(data["predictions"]) == data["test_size"]
        pred = data["predictions"][0]
        assert "actual" in pred
        assert "predicted" in pred
        assert "residual" in pred

    def test_train_temporal_split(self, client, db_session):
        # Seed with dates spanning 2022-2024
        for i in range(40):
            year = 2022 + (i // 15)
            prop = Property(
                address=f"{i + 1} Date St, SW1A 1AA",
                postcode="SW1A 1AA",
                bedrooms=(i % 4) + 1,
                bathrooms=1,
            )
            db_session.add(prop)
            db_session.flush()
            db_session.add(Sale(
                property_id=prop.id,
                price_numeric=300000 + i * 5000,
                date_sold_iso=f"{year}-06-{(i % 28) + 1:02d}",
            ))
        db_session.commit()

        resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": ["bedrooms", "bathrooms"],
            "model_type": "lightgbm",
            "split_strategy": "temporal",
            "split_params": {"cutoff_date": "2024-01-01"},
        })
        assert resp.status_code == 200
        data = resp.json()
        # Train set should be pre-2024, test set 2024+
        assert data["train_size"] > 0
        assert data["test_size"] > 0


class TestTrainXGBoost:
    def test_train_xgboost(self, client, db_session):
        _seed_properties(db_session, count=35)
        resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": ["bedrooms", "bathrooms"],
            "model_type": "xgboost",
            "split_strategy": "random",
            "split_params": {"test_ratio": 0.2},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "model_id" in data
        assert data["train_size"] > 0
        assert len(data["predictions"]) > 0


class TestPredict:
    def test_model_not_found(self, client, db_session):
        _seed_properties(db_session, count=1)
        resp = client.get("/api/v1/model/fake1234/predict?property_id=1")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_property_not_found(self, client, db_session):
        # Train a model first
        _seed_properties(db_session, count=35)
        train_resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": ["bedrooms", "bathrooms"],
            "model_type": "lightgbm",
        })
        model_id = train_resp.json()["model_id"]

        resp = client.get(f"/api/v1/model/{model_id}/predict?property_id=9999")
        assert resp.status_code == 404

    def test_predict_single(self, client, db_session):
        _seed_properties(db_session, count=35)
        # Train a model
        train_resp = client.post("/api/v1/model/train", json={
            "target": "price_numeric",
            "features": ["bedrooms", "bathrooms"],
            "model_type": "lightgbm",
        })
        assert train_resp.status_code == 200
        model_id = train_resp.json()["model_id"]

        # Predict for property 1
        resp = client.get(f"/api/v1/model/{model_id}/predict?property_id=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["property_id"] == 1
        assert "predicted_value" in data
        assert isinstance(data["predicted_value"], float)
        assert "address" in data
