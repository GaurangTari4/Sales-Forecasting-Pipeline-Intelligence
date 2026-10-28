# Business-brief actor traceability

| Actor | Workflow supported | Access boundary / limitation |
|---|---|---|
| Customer / prospect | Indirectly represented by Account and Opportunity records; no customer portal. | Out of scope: no end-user authentication, self-service access, or externally sourced customer data is implemented. |
| Marketing / sales operations | Uses Pipeline Explorer, Scenario Planner, forecast contributions, quota comparison, and exception evidence. | Local demo only; all access is unauthenticated. |
| Support agent | Can inspect exception explanations and affected entities through the Risk and Exceptions view. | Out of scope: no ticketing integration, case workflow, or permission boundary. |
| Analyst | Runs historical evaluation, reviews snapshot lineage, exports deterministic CSV/JSON, and audits validation reports. | Synthetic data only; results must not be interpreted as production accuracy. |
| System administrator | Runs isolated Compose, migrations, idempotent seed, safe health checks, and disposable `*_test` integration tests. | Must supply secrets through environment variables and must not use destructive volume commands. |

The project intentionally does not claim interactive authentication or role-based access control. Those are deployment prerequisites, not implemented capabilities.
