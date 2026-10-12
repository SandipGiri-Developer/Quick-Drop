# QuickDrop Rider Payout Dispute Desk

QuickDrop Rider Payout Dispute Desk is an automated support and dispute resolution system for quick delivery riders. The application handles questions regarding missing surge pay, wrong deductions, incentive shortfalls, and distance discrepancies. It pairs an AI agent for natural conversation with a deterministic backend for all financial calculations and policy enforcement.

## Architecture

The system maintains a strict division of responsibility between the language model and deterministic backend code.

### Model Responsibilities

1. Understand rider intent from messages in English, Hindi, and Hinglish.
2. Extract trip identifiers, dates, and dispute reasons from conversations.
3. Request clarification when the rider provides incomplete information.
4. Compose natural, empathetic explanations and updates for riders.

The language model never calculates monetary figures, never determines dispute eligibility, and never authorizes disbursements.

### Deterministic Backend Responsibilities

1. Fare Calculation: Accurately calculates expected earnings, incentives, and deductions using standard bankers rounding.
2. Policy Rules: Enforces the seven day dispute window, the 200 rupee daily autopay ceiling per rider, and single dispute per day limits.
3. Ledger Reconciliation: Queries the PaySwift ledger directly to verify existing payouts and avoid duplicate transactions.
4. Idempotency: Deduplicates incoming webhook messages and guards payout approval actions with database locks.
5. Rate Limiting: Manages outbound request pacing and retries to maintain reliable external provider communication.

## Getting Started

1. Build the container images:
```bash
docker compose build
```

2. Start the services:
```bash
docker compose up
```

This starts the FastAPI service, the PostgreSQL database, and the PaySwift mock ledger.

3. Open the Operations Dashboard:
Visit http://localhost:8000/ops in your browser to view pending approvals, recent disputes, live traces, and system health status.

## Testing and Evaluation

Run the automated test suite inside the application container:
```bash
docker compose exec app pytest
```

Run the end to end evaluation scenarios:
```bash
docker compose exec app python evals/run.py http://localhost:8000
```

## Application Endpoints

POST /messages: Accepts incoming rider chat messages and returns the assistant response.

GET /ops: Web interface for human operators to inspect system status and review cases.

GET /ops/pending: Returns disputes requiring human operator review and manual approval.

GET /trace/{rider_id}: Returns structured execution traces for a given rider session.

GET /health: Readiness probe that returns status 200 when all components are healthy.
