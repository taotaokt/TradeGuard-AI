# Frontend

The frontend is a lightweight, responsive HTML/CSS/JavaScript workspace served directly by FastAPI. It intentionally has no Node build step, which keeps the portfolio demo easy to run.

It includes sign-in, dashboard metrics, counterparty and transaction creation, assessment submission and lookup, review queue, alert center, portfolio rescreening, transaction-outcome capture, model-drift snapshots, an administrator operations workspace for schedules and notification health, PDF download, and audit history. API access uses a bearer token stored in `sessionStorage`; production deployment should add a stricter browser-session and CSRF design after a security review.

Start the application with `make run`, then open <http://localhost:8000>.
