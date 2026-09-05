# T03 Geocoding Failure Handoff

## Current issue

`scripts/evaluate.sh --llm-concurrency 8` completed parsing for the Ornith
Text2SQL evaluation, then failed during `geocode_addresses`.

- Failure: `geopy.exc.GeocoderUnavailable`, caused by a read timeout after
  geopy's default 1 second.
- Address at failure: `Chiến Lược, Bình Tân, Cần Thơ`.
- Log: `logs/official/evaluation_ornith-ai_Ornith-1.5-9B-NVFP4_text2sql_2026-09-04T235025+0700.err`.
- Preserved evaluation state: 2,800 parser records (2 explicit parse failures)
  and 16 cached geocodes (12 found, 4 not found). No evaluation seal exists.
- Rerunning is safe: parsing is complete, and geocoding resumes from
  `results/evaluation/ornith-ai/Ornith-1.5-9B-NVFP4/text2sql/geocodes.json`.

## Root cause and relevant policy

`run_evaluation.py` constructs `Nominatim` without a timeout override and calls
it directly without retry/rate limiting. geopy therefore uses a 1-second
timeout. The public Nominatim policy also requires an absolute maximum of one
request per second, a custom User-Agent, single-threaded bulk requests, and
local caching. The current evaluator already uses one thread, a custom
User-Agent, and persistent JSON caching, but does not enforce the request rate.

- Policy: <https://operations.osmfoundation.org/policies/nominatim/>
- geopy `RateLimiter`: <https://geopy.readthedocs.io/en/stable/#geopy.extra.rate_limiter.RateLimiter>
- GS-QA paper context: `references/main.tex` uses Nominatim for predicted
  address geocoding and explicitly notes that this step may be inaccurate.

## Minimal fix instruction

Use the installed geopy primitives; add no dependency or new subsystem.

1. Construct `Nominatim` with a 10-second timeout.
2. Wrap its synchronous `geocode` method with `geopy.extra.rate_limiter.RateLimiter`:
   `min_delay_seconds=1`, `max_retries=2`, `error_wait_seconds=5`, and
   `swallow_exceptions=False`.
3. Pass that callable into `load_geocodes`; after retries are exhausted, keep
   the existing behavior of aborting without an evaluation seal.
4. Preserve confirmed `not_found` results and successful geocodes exactly as
   they are. Never turn a transient service error into `not_found`.
5. Add one focused offline check with a fake transient geocoder; do not contact
   Nominatim from tests.
6. Run Ruff, Python compilation, `scripts/check_evaluator.py`, ShellCheck for
   `scripts/evaluate.sh`, and verify all raw artifact hashes remain unchanged.
7. Resume with `./scripts/evaluate.sh --llm-concurrency 8`; do not rerun raw
   inference or delete the partial evaluation files.

## Constraints

- Keep the fixed parser `ornith-ai/Ornith-1.5-9B-NVFP4` and evaluation seal v2.
- Keep raw and evaluation seals separate.
- Do not add async code, parallel geocoding, a provider abstraction, proxy,
  registry, tracker, or new provenance system.
- Do not use inline/heredoc Python or SQL, lint suppressions, or formatter
  workarounds.
- T03 remains `in_progress`; release publication waits for all four valid
  evaluation seals.

## Resolution (2026-09-05)

Applied as prescribed: `Nominatim(timeout=10)` wrapped in
`RateLimiter(min_delay_seconds=1, max_retries=2, error_wait_seconds=5,
swallow_exceptions=False)`, passed as a callable into `load_geocodes`; the
offline check covers retry-then-succeed and abort-without-poisoned-cache.
Ornith Text2SQL completed and sealed (749 geocodes: 435 found, 301 not_found,
13 rejected).

Two follow-on defects surfaced once geocoding could finish, both fixed and
recorded in `docs/plans/T03-official-v3-evaluation.md`:

1. Oversized multi-address predictions get HTTP 400/414 from Nominatim.
   Per user decision they are terminal `rejected` records (verbatim address +
   minimal reason, never re-queried, excluded from spatial matching);
   `not_found` stays reserved for confirmed nulls; timeouts/5xx/429 still
   abort without a seal.
2. `gold_values` entity keys omitted `lake_name`, so 78 T11/T12 questions
   had empty gold lists and crashed `best_text`. Key added; `best_text` now
   guards empty golds.

The remaining evaluation pairs resume with `./scripts/evaluate.sh
--llm-concurrency 8` whenever the external parser endpoint is available.

**Final (2026-09-05):** all four evaluation pairs completed and sealed; every
evaluation and raw seal validates, an idempotent `evaluate.sh` rerun skips all
pairs, and a frozen rerun of one pair reproduced its artifacts byte-identically.
`evaluation-results.tar.gz` is published and download-verified on the
`data-v3.0.0` release; T03 is done.
