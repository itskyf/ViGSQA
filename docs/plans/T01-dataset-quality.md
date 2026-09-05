# T01 — Trustworthy Vietnamese Benchmark

**Status: done (re-frozen as v1.0.0, 2026-08-28).** Published as the `v1.0.0` GitHub Release asset.

## Goal

A frozen Vietnamese GeoQA benchmark whose gold answers are reproducible from a pinned OSM snapshot, with provenance simple enough to state in one line: **dataset version, OSM snapshot, seed, counts, public URL**. Generator/verifier bytes, git commits, and per-run lineage bookkeeping are deliberately not part of the contract.

## Frozen Contract — v1.0.0

| Field | Value |
| --- | --- |
| Version | `v1.0.0` (2026-08-28) |
| Snapshot | `vietnam-260825.osm.pbf` (sha256 `99ab8080…`, pinned Geofabrik dated extract) |
| Seed / command | 42 · `python generator/generator_vi.py --seed 42 --count 100 --output data/v1.0.0/questions_vi` |
| Size | 8 files × 100 questions, stable string ids `{type}-{NNN}` |
| Distribution | GitHub Release asset, restored by `scripts/restore_dataset.sh` (sha256-verified against `scripts/v1.0.0.sha256`) |
| Provenance | `data/v1.0.0/questions_vi/MANIFEST.json` |

An earlier internal freeze (2026-08-27) of the identical question bytes carried heavy provenance machinery (generator/verifier hash pinning, commit-lineage resolution) and was invalidated; this freeze replaces it wholesale as `v1.0.0`. Because the jsonl bytes are unchanged (same seed + snapshot, regeneration compared byte-for-byte), the 80/80 human QC review applies as-is.

## Validation (2026-08-28)

- `generator/verify_vi.py --all`: **800/800 passed** (NFC, placeholders, length, diacritic surfaces, OSM names, anchor exclusion, deterministic ordering).
- Regeneration diff vs the previous freeze: 8/8 jsonl byte-identical.

## Recorded Limitations (kept, not fixed)

- OSM snapshot quirks the SQL faithfully reflects: tag reuse (billiards club under `leisure=sports_centre`, resorts under `swimming_pool`, laptop store under `shop=supermarket`), mapper typos in POI names, remote-anchor nearest-neighbour distances up to ~140 km in sparse provinces.
- Template characteristics: some loc surfaces say "địa chỉ nào?" while gold is coordinates; "dưới N km" vs inclusive `ST_DWithin` differs only at the edge; occasional redundant question tails.
- Heavy-tail cardinality is a dataset characteristic, not a defect: range gold sets reach 1254 answers (medians single-digit); scoring must use best-match against the full set (T03).

## Regeneration

Export the `PostgresSettings` defaults (`PGHOST=127.0.0.1`, `PGPORT=5432`,
`PGDATABASE=osm_vn`, `PGUSER=postgres`, `PGPASSWORD=postgres`), then run the
pinned download, initialization, and import scripts followed by the command
above from the repo root. `vietnam-latest` never reproduces a frozen version.
