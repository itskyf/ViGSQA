# T08 — Fast Database Bootstrap via Prebuilt Release Dump

**Status: done (2026-08-29).**

## Goal

Cut the fresh-environment database bootstrap (especially Colab, where the 327 MB snapshot download,
osmium scan, and osm2pgsql run dominate startup) by restoring a prebuilt plain-SQL dump published on the
GitHub Release `v2.0.0`, with the existing pinned-snapshot osm2pgsql import kept as the fallback.
Priority: **restore > build**.

## Design Decisions

- **Plain-SQL dump, not custom/directory format.** The dump is produced locally by PostgreSQL 18.6
  (compose `postgis/postgis:18-3.6`) and must restore onto Colab's apt PostgreSQL 14 + PostGIS 3.4.
  PG18's `pg_restore` archives are not readable by PG14, and older `pg_dump` clients refuse newer
  servers — a plain-SQL dump piped through the *target's own* `psql` is the only cross-version-safe shape.
  Geometry ships as hex EWKB inside COPY blocks, which is PostGIS-version-independent. Measured:
  282,532,006 B raw → 121,322,941 B gzipped (default level); GitHub's per-asset limit is 2 GiB.
- **The artifact stays a pristine pg_dump; the restore script owns target quirks.** Exactly five
  emitted lines are incompatible with PG14 (exhaustive, grep-verified): `SET transaction_timeout = 0;`
  (PG17+ GUC), the `\restrict`/`\unrestrict` psql-meta-command pair (PG18.x client command), and the
  `DROP SCHEMA IF EXISTS public;`/`CREATE SCHEMA public;` pair that `--clean` emits and that would
  otherwise collide with the postgis extension already installed in `public` by `init_database.sh`/
  compose. `scripts/restore_database.sh` deletes exactly those patterns with sed before piping to
  `psql --set=ON_ERROR_STOP=1`. COPY data can never match them (hex/tab-separated text).
- **Content-identity lineage: `source_size`/`source_mtime` are dropped codebase-wide.** The import
  marker and the `.osm_vn_fileinfo` osmium-scan cache both key on `filename + sha256` (+ `style_sha256`
  for the marker) instead of size+mtime. A maintainer-local mtime was meaningless once the marker row
  began shipping inside the dump; sha256 is machine-independent and strictly stronger as a cache key.
  Verified contained to `scripts/import_osm.sh` and three files under `sql/` — no notebook, Python, or
  doc consumer.
- **Probe is existence-only and variable-free.** `sql/check_database_populated.sql` returns 1 iff all
  11 reference objects (5 tables, 5 views, marker) exist. `sql/check_import.sql` cannot serve the fast
  path: it requires PBF-derived psql variables (size/mtime previously; now sha) that do not exist on a
  fresh machine. Tables restore before views, so an interrupted restore probes "not populated", and the
  dump's own `--clean ... IF EXISTS` section drops partial objects on retry — restore is self-healing.
- **URL and sha256 are pinned constants, not env-overridable.** They are a verification pair; an
  overridable URL behind a pinned checksum would either break verification or invite unverified
  restores. (`restore_dataset.sh`'s `DATASET_URL` override is safe only because it re-verifies against
  a per-file manifest afterwards; the DB asset has no such manifest.) Same idiom as `download_osm.sh`.
- **Snapshot lineage uses Geofabrik's own md5 sidecar, not a repo-pinned sha256.** `download_osm.sh`
  fetches `vietnam-260825.osm.pbf.md5` and verifies against it, and the import marker plus the
  `.osm_vn_fileinfo` osmium-scan cache key on that md5 (`filename + source_md5`, plus `style_sha256`
  for the marker). The local file's md5 (`620d0258ffecd450363e24560d0a7b8b`) matches the live sidecar,
  and the same file carries the previously pinned sha256 (`99ab8080…`) — chain of custody unchanged.
  The lua style keeps its sha256 (no upstream reference exists for it). No
  backward-compat shims exist for older marker shapes (`init_marker.sql` is a
  plain `CREATE TABLE IF NOT EXISTS`) — explicitly out of scope by decision.
- **The dump artifact is byte-deterministic.** pg_dump 18 randomizes the `\restrict`/`\unrestrict`
  tokens per run, which changed the compressed bytes on every export; `export_database.sh` normalizes
  both tokens to a fixed value (the restore filters delete those lines outright), so re-exporting an
  unchanged database reproduces the exact published asset — verified by two consecutive exports
  producing the same SHA-256. `export_database.sh` also refuses to upload unless
  `restore_database.sh` pins the artifact's checksum, keeping the URL/checksum pair honest.
- **No notebook code change.** `main-v2.ipynb` delegates DB setup to `scripts/bootstrap_postgres.sh`,
  so the fast path activates automatically; only a markdown note documents the two paths.
- **`DB_RESTORE=0` forces the raw import path** for debugging. A restore that exits 0 but fails the
  bootstrap count gate still fails bootstrap loudly — no silent fallback to the 8-minute import after
  a "successful" but wrong restore.

## Validation

All evidence gathered 2026-08-29 against the pinned snapshot import (G1 counts:
pois 38,223 · regions 8,535 · parks 1,492 · lakes 7,973 · roads 175,318).

- **md5 lineage re-import**: after dropping `source_size`/`source_mtime`, one re-import plus one
  osmium rescan reproduced the exact G1 counts; the marker row holds `source_md5 =
  620d0258ffecd450363e24560d0a7b8b` (== Geofabrik sidecar) and the legacy columns are dropped; the
  immediate re-run logs `Already imported` with no rescan.
- **Artifact audit**: exactly the five PG14-incompatible line patterns occur in the dump (one each);
  the only backslash meta-commands in the whole 231k-line dump are the restrict pair; every other
  emitted `SET` GUC predates PG14. Size 121,322,845 B; SHA-256
  `377976f2bc3e8a78ea17f46bebfec8413123d44221100e773da8d70053fc2e16` (pinned in
  `restore_database.sh`).
- **Local PG18 scratch restore**: fresh `osm_vn_restore_test` + postgis, restore via the script
  (cached-file skip, sed filter, `ON_ERROR_STOP`) → exact G1 counts; immediate re-run logs
  `already populated; skipping restore`.
- **Cross-version acceptance (PostgreSQL 14.18 / PostGIS 3.5.2 container)**: restore of the exact
  published artifact with the container's own psql 14 client (`ON_ERROR_STOP=1`) → rc 0, exact G1
  counts, all 10 GiST indexes present, `pois` geography KNN around Hanoi works (identical results to
  PG18: `Brgmart` 29 m / `Cà Phê Affett` 35 m / `Khách Sạn Golden Sun Villa` 46 m). The Colab code
  branch (direct `psql` on `PG*` env, `COLAB_RELEASE_TAG` set) was executed inside the same container
  against a fresh database → rc 0, exact G1 counts.
- **Download path from a clean cache**: with the local dump deleted, the wired bootstrap downloaded
  the release asset, verified SHA-256, restored, and passed the gate with exact G1 counts — the full
  fresh-environment path minus Colab's own postgres install.
- **Bootstrap regression**: normal run → probe skip + gate pass; `DB_RESTORE=0` run → md5-verified
  snapshot skip, `Already imported`, gate pass (the `run_official_v2.sh` preflight shape).
- **Publishing**: `gh release view v2.0.0` lists `osm-vn-v2.0.0.sql.gz` (121,322,845 B) beside
  the dataset zip. Static checks: ShellCheck clean on all four scripts, `sqlfluff lint sql/` clean,
  Ruff clean on `run_check_v2.py`, and `osm_snapshot()` there now records `url` + local-file `md5`
  (schema change of the run manifest; no full-run manifests existed yet — W7 had not started).
- **Notebook**: `main-v2.ipynb` §1.1 markdown now names the restore-first behavior and `DB_RESTORE=0`;
  no code change (the notebook delegates to `scripts/bootstrap_postgres.sh`). Sync the Drive copy
  before the next Colab run.

## Deliberate Skips

- No dump/restore parallelism: single-stream gzip+psql is I/O-bound at this size; `nproc` parallelism
  already lives in the osm2pgsql fallback.
- `install_dependencies.sh` still apt-installs osm2pgsql/osmium on Colab even when the fast path
  succeeds — fallback readiness beats the ~60 s saved.
- No zstd: gzip is universally present, no new dependency.
- The probe checks existence, not counts — the bootstrap gate owns counts (the asset is sha-pinned, so
  an error-free restore implies correct data).
- If a PostGIS 3.4/3.5 target ever rejects the 3.6-authored view DDL: fallback design is a tables-only
  dump plus running `sql/refresh_views.sql` on the target. Not built unless needed.

## Addendum: custom-format dump + parallel restore (2026-09-05)

The plain-SQL decision above was driven by one constraint — restoring onto
Colab's apt PostgreSQL 14 — which ended when Colab moved to PGDG PostgreSQL
18/PostGIS 3.6 (T02 re-proof). The asset is now **`osm-vn.dump`**, a
`pg_dump --format=custom` archive of the same flags
(`--schema=public --exclude-extension=postgis --clean --if-exists
--no-owner --no-privileges`), restored by parallel
`pg_restore --jobs=4 --exit-on-error`:

- The TOC filter (`grep --invert-match ' SCHEMA - public '`) is the
  custom-format analogue of the old two sed schema filters: it drops the
  single `SCHEMA - public` TOC entry so the restore cannot drop/recreate the
  schema hosting the pre-created postgis extension. `--exclude-extension`
  already keeps any `EXTENSION` entry out of the archive (verified: 37 TOC
  entries, exactly one `SCHEMA - public` line). All other `--clean` entries
  stay, so interrupted restores remain self-healing.
- Local runs restore inside the compose container (binary `cat` into
  `/tmp`, then list/filter/restore there); Colab uses the host PGDG
  `pg_restore`. This reverses the "no dump/restore parallelism" skip above;
  gzip compression is kept (the "no zstd" skip stands).
- **Determinism is lost**: custom archives embed their creation timestamp, so
  every export differs. `export_database.sh` therefore now auto-pins the
  checksum into `restore_database.sh` (reviewed via git diff) instead of the
  confirm-by-rerun guard, which would loop on fresh checksums. The exporter's
  stale `data-` release-tag prefix (missed by the tag rename) is fixed in the
  same rewrite.
- Validation: scratch-DB restore in **3.65 s** with exact v3 counts
  (pois 38,207 · regions 8,567 · parks 1,493 · lakes 7,987 · roads 175,883 —
  identical to the source DB), 10 GiST indexes, pois×regions spatial join
  works, immediate re-run logs "already populated; skipping"; the published
  asset's re-download SHA-256 matches the pin.
