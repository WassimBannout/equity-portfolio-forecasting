# Portfolio forecasting

An independently designed daily stock-forecasting and portfolio-allocation
demonstrator, based on the supplied [specifications](specifications/PROJECT_SPEC.md).

**Status: Milestone 0 complete — design documents, coverage review, and minimal
repository scaffold only.** There is no runnable application, installed project
environment, database schema, CI workflow, or deployment yet.

The planned product fits independent Prophet price forecasts for twelve configured
US-listed equities, converts forecasts into expected returns, solves a constrained
mean-variance allocation using realised risk observations, publishes coherent runs
to Supabase, and presents their history in a read-only Streamlit dashboard.
Recommendations are weights; the application does not execute trades.

## Start here

| Document | Purpose |
| --- | --- |
| [Architecture](ARCHITECTURE.md) | System boundaries, data/time/ML contracts, publication and operating design |
| [Implementation plan](IMPLEMENTATION_PLAN.md) | Confirmed M0 boundary and the supplied M1–M6 delivery/test gates |
| [Decisions](DECISIONS.md) | Important choices, rationale, trade-offs, and unresolved evidence |
| [Specification coverage](SPECIFICATION_COVERAGE.md) | Product behaviors, all recommendation IDs, and acceptance-scenario mapping |
| [Milestone 0 report](MILESTONE_0_REPORT.md) | Delivered files, commands/checks, results, and limitations |
| [Supplied rebuild plan](specifications/REBUILD_PLAN.md) | Authoritative original milestone definitions |

The original reference implementation was not consulted. The seven supplied
specification files remain unchanged.

## Development boundary

Milestone 1 will add the Python package, verified interpreter/tool versions,
committed independent dependency lock, validated request/settings boundary,
meaningful configuration tests, and non-modifying quality CI. Installation and
execution commands will be documented after they are implemented and tested.

For now the scaffold consists of documentation, [.editorconfig](.editorconfig),
and [.gitignore](.gitignore). No empty application modules or placeholder passing
tests are included. Supply credentials through the appropriate process environment
when future workloads require them; never commit credential files.

Milestone 0 is the stopping point. Do not begin Milestone 1 until instructed.
