# QuickDrop Rider Payout Dispute Desk

This repository contains the complete solution for the QuickDrop Rider Payout Dispute Desk assignment.

## How to Run It

1. **Start the system**:
   ```bash
   docker compose down -v
   docker compose up --build -d
   ```
   This will spin up the FastAPI app, the PostgreSQL database, and the PaySwift sandbox.

2. **Access the Ops Dashboard**:
   Open [http://localhost:8000/ops](http://localhost:8000/ops) in your browser. This dashboard displays pending approvals, escalations, agent traces, and live AI/API health metrics.

3. **Run Evaluations**:
   ```bash
   # Run unit/integration tests
   docker compose exec app pytest -v
   
   # Run the full 24-case + adversarial evaluator
   docker compose exec -e PYTHONPATH=/app app python evals/run.py http://localhost:8000
   ```

## Agent Design

The system uses **LangGraph** and **LangChain** with the Gemini provider to orchestrate rider conversations.

### What the Model Decides
The LLM is strictly restricted to conversational understanding. It decides:
- How to extract intent (e.g., identifying the rider is asking about a missing surge).
- How to extract parameters (e.g., trip ID or date).
- When to ask clarification questions vs when to invoke a tool.
- How to format the final friendly response back to the rider in natural language/Hinglish.

**Crucially, the LLM NEVER decides payout amounts, auto-pay eligibility, or financial rules.**

### What the Code Decides
All financial and business logic is deterministic and handled entirely by the Python backend:
- **Fare Calculator**: Calculates the exact owed amount using bankers' rounding and computes discrepancies.
- **Decision Engine**: Enforces the 7-day dispute window, the ₹200 daily auto-pay limit per rider, and once-per-day constraints.
- **PaySwift Reconciliation**: Verifies past payments directly against the PaySwift ledger to prevent duplicate payouts.
- **Idempotency**: Message deduplication and idempotent approval locks are enforced at the database level.
- **Rate Limiting**: An `AiHealthTracker` interceptor ensures strict 3-4 second delays between outbound LLM requests to prevent quota exhaustion, backed by resilient retry logic.

### Tools Provided to the Agent
1. `check_discrepancies(trip_id)`: Fetches trip details and calculates any shortfall.
2. `execute_dispute_resolution(trip_id)`: Triggers the deterministic decision engine to either auto-pay via PaySwift, escalate to Ops, or require Ops approval.

## Assumptions Made
1. **Rider Identity**: The `rider_id` provided in the API payload is trusted (from the messaging vendor). If a rider claims a different identity in the text (e.g., "I am R005"), the agent ignores it and enforces security using the authenticated ID.
2. **Date Parsing**: If a rider says "20 tarikh wala", the agent assumes the current month and year based on the `received_at` timestamp.
3. **PaySwift Sandbox State**: Because the PaySwift sandbox holds state in memory, we assume a clean environment (`docker compose restart payswift`) before running isolated test suites to prevent cross-test state leakage.

## Eval Results
- **Standard Cases**: 24/24 PASS (100%)
- **Adversarial Cases**: PASS (Successfully defends against duplicate messages, story changes, and PaySwift outages).
- **Unit & Integration Tests**: 101/101 PASS (100% passing rate with full coverage of the decision engine).

## What Was Skipped
- We did not introduce heavy frontend frameworks (like React or Vue) for the Ops Dashboard. As requested, we kept the tech stack fixed to vanilla HTML/JS and FastAPI to ensure a lightweight, maintainable, and production-ready solution. 
- We did not implement a dedicated persistent memory layer across *multiple days* of chat context for the LLM; the agent relies entirely on the immediate trace and session history.
