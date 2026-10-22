# Frontend

The frontend is a lightweight, responsive HTML/CSS/JavaScript workspace served directly by FastAPI. It intentionally has no Node build step, which keeps the portfolio demo easy to run.

It includes sign-in, dashboard metrics, counterparty and transaction creation, a sourced KYB-fact register with reviewer actions, governed counterparty credit-policy versions, explainable duplicate-entity review, assessment submission and lookup, review queue, alert center, portfolio exposure and stress testing, portfolio rescreening, transaction-outcome capture, model-drift snapshots, an administrator operations workspace for schedules and notification health, a role-scoped data-quality remediation queue, approval-condition tracking with evidence, PDF download, and audit history. API access uses a bearer token stored in `sessionStorage`; production deployment should add a stricter browser-session and CSRF design after a security review.

Start the application with `make run`, then open <http://localhost:8000>.
