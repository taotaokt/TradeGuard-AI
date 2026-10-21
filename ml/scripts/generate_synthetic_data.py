import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np

from backend.app.ml_schema import FEATURE_NAMES, TARGET_NAME


DEFAULT_OUTPUT = Path("sample-data/ml/synthetic_trade_outcomes.csv")


def generate_rows(sample_count: int = 4000, seed: int = 20261021):
    rng = np.random.default_rng(seed)
    amount = np.clip(rng.lognormal(mean=10.2, sigma=1.0, size=sample_count), 1000, 2_000_000)
    amount_usd_log = np.log1p(amount)
    payment_terms_days = rng.choice(
        np.array([0, 15, 30, 45, 60, 90, 120]),
        size=sample_count,
        p=[0.08, 0.13, 0.31, 0.12, 0.22, 0.11, 0.03],
    )
    deposit_percentage = np.round(rng.beta(1.8, 3.2, size=sample_count) * 100, 2)
    exposure_ratio = np.clip(
        1 - (deposit_percentage / 100) + rng.normal(0, 0.08, size=sample_count), 0, 1.5
    )
    has_letter_of_credit = rng.binomial(1, 0.28, size=sample_count)
    has_transshipment = rng.binomial(1, 0.18, size=sample_count)
    counterparty_active = rng.binomial(1, 0.82, size=sample_count)
    transaction_document_count = np.clip(rng.poisson(2.5, size=sample_count), 0, 10)
    counterparty_evidence_count = np.clip(rng.poisson(1.7, size=sample_count), 0, 8)

    log_odds = (
        -2.75
        + 0.018 * (payment_terms_days - 30)
        - 0.012 * deposit_percentage
        + 1.15 * exposure_ratio
        - 0.75 * has_letter_of_credit
        + 0.58 * has_transshipment
        - 0.65 * counterparty_active
        - 0.10 * transaction_document_count
        - 0.12 * counterparty_evidence_count
        + 0.10 * (amount_usd_log - 10)
        + rng.normal(0, 0.30, size=sample_count)
    )
    probability = 1 / (1 + np.exp(-log_odds))
    outcome = rng.binomial(1, probability)

    matrix = np.column_stack(
        [
            amount_usd_log,
            payment_terms_days,
            deposit_percentage,
            exposure_ratio,
            has_letter_of_credit,
            has_transshipment,
            counterparty_active,
            transaction_document_count,
            counterparty_evidence_count,
            outcome,
        ]
    )
    return matrix


def write_dataset(path: Path, sample_count: int = 4000, seed: int = 20261021) -> str:
    matrix = generate_rows(sample_count=sample_count, seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(FEATURE_NAMES + [TARGET_NAME])
        for row in matrix:
            writer.writerow(["{:.8f}".format(value) for value in row])
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate public-safe synthetic trade outcomes.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20261021)
    args = parser.parse_args()
    checksum = write_dataset(args.output, sample_count=args.samples, seed=args.seed)
    print("wrote {} rows to {} (sha256={})".format(args.samples, args.output, checksum))


if __name__ == "__main__":
    main()
