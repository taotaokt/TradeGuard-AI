import json

import numpy as np

from backend.app.ml_schema import FEATURE_NAMES
from backend.app.ml_service import load_model_bundle
from ml.scripts.generate_synthetic_data import generate_rows, write_dataset


def test_synthetic_generation_is_reproducible(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first_hash = write_dataset(first, sample_count=100, seed=42)
    second_hash = write_dataset(second, sample_count=100, seed=42)
    assert first_hash == second_hash
    assert first.read_bytes() == second.read_bytes()


def test_model_artifact_is_verified_and_matches_schema():
    manifest, model = load_model_bundle()
    assert manifest["feature_names"] == FEATURE_NAMES
    assert manifest["artifact_trust"].startswith("Load only repository-generated")
    values = [
        (manifest["feature_ranges"][name]["min"] + manifest["feature_ranges"][name]["max"])
        / 2
        for name in FEATURE_NAMES
    ]
    probability = float(model.predict_proba(np.asarray([values]))[0, 1])
    assert 0 <= probability <= 1


def test_model_manifest_documents_reproducibility():
    manifest, _ = load_model_bundle()
    assert len(manifest["training_data_checksum"]) == 64
    assert manifest["calibration"] == "sigmoid, 5-fold cross-validation"
    assert set(manifest["runtime"]) == {"python", "numpy", "scikit_learn", "joblib"}
    assert json.loads(json.dumps(manifest["metrics"]))["logistic_baseline"]["brier_score"] < 0.1


def test_same_seed_produces_identical_matrix():
    assert np.array_equal(generate_rows(25, 123), generate_rows(25, 123))
