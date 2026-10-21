import hashlib
import json
import math
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ml_schema import FEATURE_NAMES, RISK_BAND_THRESHOLDS
from backend.app.models import ModelVersion, SupportingDocument, TradeTransaction


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "ml" / "artifacts" / "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def load_model_bundle() -> Tuple[dict, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("feature_names") != FEATURE_NAMES:
        raise RuntimeError("Model feature schema does not match the application schema")
    artifact = PROJECT_ROOT / manifest["artifact"]["path"]
    expected = manifest["artifact"]["sha256"]
    if not artifact.is_file() or _sha256(artifact) != expected:
        raise RuntimeError("Model artifact is missing or failed SHA-256 verification")
    return manifest, joblib.load(artifact)


def register_model_version(db: Session, manifest: dict) -> ModelVersion:
    existing = db.scalar(
        select(ModelVersion).where(ModelVersion.version == manifest["model_version"])
    )
    if existing:
        if existing.artifact_sha256 != manifest["artifact"]["sha256"]:
            raise RuntimeError("Model version changed without a new version identifier")
        return existing
    trained_at = datetime.fromisoformat(manifest["trained_at"].replace("Z", "+00:00")).replace(
        tzinfo=None
    )
    item = ModelVersion(
        version=manifest["model_version"],
        name=manifest["champion_model"],
        model_type="calibrated_classifier",
        status=manifest["status"],
        target_definition=manifest["target_definition"],
        feature_schema_json=json.dumps(manifest["feature_names"]),
        metrics_json=json.dumps(manifest["metrics"], sort_keys=True),
        artifact_path=manifest["artifact"]["path"],
        artifact_sha256=manifest["artifact"]["sha256"],
        training_data_sha256=manifest["training_data_checksum"],
        runtime_json=json.dumps(manifest["runtime"], sort_keys=True),
        trained_at=trained_at,
    )
    db.add(item)
    db.flush()
    return item


def extract_features(db: Session, transaction: TradeTransaction) -> Dict[str, float]:
    amount = max(float(transaction.amount), 0.01)
    exposure = float(transaction.requested_credit_exposure or Decimal("0"))
    counterparty_ids = {
        party.counterparty_id for party in transaction.parties if party.counterparty_id
    }
    transaction_documents = db.scalar(
        select(func.count(SupportingDocument.id)).where(
            SupportingDocument.transaction_id == transaction.id,
            SupportingDocument.status == "active",
        )
    ) or 0
    counterparty_evidence = 0
    if counterparty_ids:
        counterparty_evidence = db.scalar(
            select(func.count(SupportingDocument.id)).where(
                SupportingDocument.counterparty_id.in_(counterparty_ids),
                SupportingDocument.status == "active",
            )
        ) or 0
    # Screening state is reflected by the status cached on linked Counterparty rows.
    from backend.app.models import Counterparty

    counterparties = [db.get(Counterparty, identifier) for identifier in counterparty_ids]
    all_active = bool(counterparties) and all(item and item.status == "active" for item in counterparties)
    payment_method = transaction.payment_method.casefold().replace("-", "_").replace(" ", "_")
    features = {
        "amount_usd_log": math.log1p(amount),
        "payment_terms_days": float(transaction.payment_terms_days),
        "deposit_percentage": float(transaction.deposit_percentage),
        "requested_credit_exposure_ratio": max(exposure / amount, 0.0),
        "has_letter_of_credit": float("letter_of_credit" in payment_method),
        "has_transshipment": float(bool(transaction.transshipment_country)),
        "counterparty_active": float(all_active),
        "transaction_document_count": float(transaction_documents),
        "counterparty_evidence_count": float(counterparty_evidence),
    }
    if list(features) != FEATURE_NAMES or not all(math.isfinite(value) for value in features.values()):
        raise RuntimeError("Extracted model features are invalid")
    return features


def _reason_codes(features: Dict[str, float]) -> List[str]:
    checks = [
        (features["payment_terms_days"] > 60, "LONG_PAYMENT_TERMS"),
        (features["deposit_percentage"] < 15, "LOW_DEPOSIT"),
        (features["requested_credit_exposure_ratio"] > 0.8, "HIGH_EXPOSURE_RATIO"),
        (not features["has_letter_of_credit"], "NO_LETTER_OF_CREDIT"),
        (bool(features["has_transshipment"]), "TRANSSHIPMENT_ROUTE"),
        (not features["counterparty_active"], "COUNTERPARTY_NOT_ACTIVE"),
        (features["transaction_document_count"] < 1, "LIMITED_TRANSACTION_DOCUMENTS"),
        (features["counterparty_evidence_count"] < 1, "LIMITED_COUNTERPARTY_EVIDENCE"),
    ]
    return [code for triggered, code in checks if triggered]


def predict_transaction(db: Session, transaction: TradeTransaction) -> dict:
    manifest, model = load_model_bundle()
    features = extract_features(db, transaction)
    matrix = np.asarray([[features[name] for name in FEATURE_NAMES]], dtype=float)
    probability = float(model.predict_proba(matrix)[0, 1])
    thresholds = RISK_BAND_THRESHOLDS
    risk_band = (
        "critical" if probability >= thresholds["high"] else
        "high" if probability >= thresholds["medium"] else
        "medium" if probability >= thresholds["low"] else "low"
    )
    out_of_range = [
        name for name, value in features.items()
        if value < manifest["feature_ranges"][name]["min"]
        or value > manifest["feature_ranges"][name]["max"]
    ]
    nearest = min(abs(probability - value) for value in thresholds.values())
    confidence = "low" if out_of_range else "medium" if nearest < 0.025 else "high"
    uncertainty = (
        "Out-of-training-range features: {}".format(", ".join(out_of_range))
        if out_of_range else
        "Probability is close to a risk-band threshold" if confidence == "medium" else None
    )
    return {
        "manifest": manifest,
        "probability": probability,
        "risk_band": risk_band,
        "confidence": confidence,
        "uncertainty_reason": uncertainty,
        "reason_codes": _reason_codes(features),
        "features": features,
    }
