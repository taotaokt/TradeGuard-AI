# Reproducible modeling report

## Research question

Can a transparent, calibrated baseline support triage of commercial payment risk while preserving deterministic compliance and policy controls?

## Experimental design

The repository generates 4,000 synthetic trade-outcome rows with a fixed seed. The target represents a synthetic severe delinquency or material loss event. Features describe transaction size, payment terms, deposit, requested exposure, payment instrument, transshipment, counterparty status, and evidence counts. No real people, companies, invoices, credit files, or confidential family-business records are used.

Data is split into stratified 75% training and 25% testing partitions. The candidates are logistic regression with standardized inputs and a constrained random forest. Each candidate receives five-fold sigmoid probability calibration. Selection prioritizes the lowest held-out Brier score and uses ROC AUC as a tie-breaker.

## Current result

The calibrated logistic regression is the champion. On the generated held-out sample it achieved ROC AUC 0.738, average precision 0.154, Brier score 0.048, log loss 0.189, and ten-bin expected calibration error 0.004. The event rate was 5.3%. These results describe only this synthetic generator and are not evidence of real-world credit performance.

## Reproducibility

```bash
python3 -m ml.scripts.generate_synthetic_data
python3 -m ml.scripts.train_models
python3 -m pytest backend/tests/test_ml.py
```

The manifest records the seed, feature order and ranges, target definition, split sizes, dependency versions, metrics, training-data checksum, and artifact checksum. Inference refuses an artifact whose SHA-256 digest does not match the manifest.

## Governance and limitations

Feature flags returned with a prediction are policy-oriented observations, not causal explanations. Inputs outside the training range receive low confidence and are referred to a person. A real deployment would require legally obtained outcome data, temporal validation, leakage analysis, subgroup testing, stability and drift monitoring, independent validation, documented approval, and periodic review. Compliance screening remains a separate hard-stop process.
