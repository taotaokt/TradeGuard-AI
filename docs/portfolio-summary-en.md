# TradeGuard AI - portfolio summary

TradeGuard AI is an explainable risk-decision workspace for small cross-border trading businesses. I built it to connect the parts that are often fragmented across spreadsheets: counterparty onboarding, document evidence, restricted-party screening, commercial terms, deterministic rules, statistical risk estimation, human review, and audit history.

The system is a FastAPI and SQLAlchemy modular monolith with Alembic migrations, role-based access, PostgreSQL/SQLite support, a no-build responsive frontend, and downloadable PDF reports. Its ML pipeline generates a versioned public-safe synthetic dataset, compares calibrated logistic regression and random forest candidates, selects a champion using held-out calibration and discrimination metrics, verifies artifact checksums at inference, and routes out-of-range inputs to review. Portfolio analytics keep currencies separate and persist reproducible, non-decisioning stress-test snapshots.

The most important product choice is separation of authority: a model score can inform commercial-risk review, but it cannot clear a compliance hold. Every assessment stores the input snapshot, list versions, rule checksum, model version, prediction features, reasons, recommendation, and reviewer action.

This project demonstrates full-stack engineering, applied ML, model governance, product judgment, testing, and clear communication about limitations. It is a portfolio system, not a claim that synthetic model performance transfers to real credit decisions.
