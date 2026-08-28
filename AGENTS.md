# AGENTS.md

## Repository Context

- This repository is a Vietnamese adaptation of an upstream research codebase. Apply these standards to new or substantially rewritten code. Do not rewrite upstream-derived scripts only for style; keep necessary changes focused and preserve experimental behavior.
- The primary workflow is synchronous batch, CLI, and notebook execution with PostgreSQL/PostGIS, including Google Colab. Do not introduce async, Ray, or a configuration framework unless the active task requires it.
- Internal APIs may change freely. Dataset schemas, question IDs, prompts, seeds, metric semantics, and recorded experiment artifacts are reproducibility interfaces: document changes and regenerate or version affected artifacts.
- Frozen datasets under `data/` are deliberately outside version control (mirrored externally, restorable byte-identically via the pinned seed; contract in `docs/plans/T01-dataset-quality.md`). Read them through the `generator/questions_vi` symlink and never commit files under `data/`.
- Use only language features supported by the pinned notebook runtime. Runtime consolidation belongs to the project plan until that environment is pinned.

## Agent Skills

Use subagents for parallelizable or well-scoped work such as surveying a subsystem or running independent ablations.

## Planning Workflow

- `docs/PLAN.md` is the authoritative project plan.
- Before starting work, read `docs/PLAN.md`, the active task record under `docs/plans/`, the repository state, and relevant results.
- When activating a planned task, create its task record under `docs/plans/` before starting implementation.
- Future tasks describe goals and motivation only. Do not prescribe implementations, artifacts, metrics, or outputs before evidence or an external requirement makes them necessary. Externally imposed contracts (course rubric structure, frozen-benchmark invariants, reproducibility interfaces) are recorded in task records, not deferred as open questions.
- Treat plans as living documents. Update them when experiments, tests, data, or investigation produce new evidence.
- Work toward the task goal and prefer root-cause investigation over workarounds.
- Record meaningful findings, decisions, validation, and unresolved questions in the active task record.
- Keep runtime state (service locations, host-specific paths, live-session details) out of `docs/PLAN.md` and task records; document environment setup in README or how-to docs instead.
- Before ending a session, update `docs/PLAN.md` with the task status, concise progress, cross-task discoveries, and next logical action.
- Valid statuses are `planned`, `in_progress`, `blocked`, and `done`. Mark a task `done` only after its goal is satisfied and relevant validation passes.
- Keep `docs/PLAN.md` concise and detailed investigation in task records. Preserve useful history and record why a direction changed. A task's `Next` section is the best current step, not a contract.
- If a task is unclear, conflicts with repository evidence, or reveals a suspicious result that could change its scope or direction, record the evidence and ask the user to review that task before proceeding.

## Coding Standards

- Do not over-engineer or extract code before meaningful duplication occurs. Keep paths flat, prefer guard clauses, and fix root causes rather than symptoms.
- Prefer concrete types and structured records. Exact third-party protocol or override signatures may use required types such as `Any`.
- Pass runtime configuration from entrypoints. Prefer CLI arguments, environment variables, and module constants already used by the repository; never use mutable global state.
- Safe local defaults are acceptable. Never default secrets, credentials, or personal filesystem paths.
- Add focused validation when changes affect dataset correctness, SQL generation, evaluation metrics, or reproducibility. Do not add broad test scaffolding for presentation-only changes.

### Code Comments

- Write comments in English.
- Explain why, assumptions, invariants, edge cases, and non-obvious tradeoffs. Do not restate the code.
- Keep comments accurate when code changes. Prefer a condensed block comment above tricky code.
- Use `TODO:` only for a temporary workaround or known follow-up, with an issue, link, or clear owner/context.

### Output and Logging

- `print` is acceptable for user-facing CLI, notebook, report, and progress output.
- Reusable modules use `logging.getLogger(__name__)` for diagnostics. Leave logging configuration to entrypoints and use lazy formatting such as `logger.info("msg %s", value)`.
- Use `logger.exception()` in exception handlers when a stack trace is useful.
- Do not add calculations solely for logging or emit high-frequency noise. Never log secrets, tokens, or credentials.

### Docstrings and Maintenance

- Use Google-style docstrings with Markdown. Use single backticks for code and variables and LaTeX such as $f(x)$ for math; do not use reStructuredText fields or double backticks.
- Docstrings are required for public APIs and complex logic and optional for self-explanatory private helpers.
- Rely on type hints rather than repeating types in docstrings. Omit `Returns:` when returning `None`.
- Update docstrings whenever a signature, return value, or documented behavior changes.
