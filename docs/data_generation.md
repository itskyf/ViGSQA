# Data Generation — VN-GeoQA

## Overview

VN-GeoQA contains 800 Vietnamese geospatial questions generated automatically from OpenStreetMap Vietnam data stored in a PostGIS database. Questions are paired with ground-truth SQL queries and answers verified against the live database.

---

## Pipeline

```text
OSM Vietnam (.pbf)
       │
       ▼
 osm2pgsql → PostGIS DB (osm_vn)
       │
       ▼
 generator_vi.py
  ├── query DB for real POI names + coordinates
  ├── fill Vietnamese templates (templates_vi/*.txt)
  ├── execute SQL to verify answer exists
  └── save to questions_vi/*.jsonl
       │
       ▼
 verify_vi.py  (spot-check 5% of questions)
```

---

## Step 1 — Database Setup

Local (PostGIS runs in the `compose.yaml` container; tools come from pixi):

```bash
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=osm_vn
export PGUSER=postgres PGPASSWORD=postgres
./scripts/install_dependencies.sh
podman compose up -d postgres
./scripts/init_database.sh
./scripts/download_osm.sh    # ~312 MB Geofabrik extract
./scripts/import_osm.sh
```

`install_dependencies.sh` only installs or verifies dependencies. In Google
Colab it uses apt for PostgreSQL/PostGIS and the required import tools; service
startup and database initialization are separate steps. The course notebook
runs the PostgreSQL/OSM workflow independently from llama.cpp and waits for
both branches before exploration or experiments. After bootstrap, bounded
readiness and PostGIS checks use psycopg3; `psql` is used only where Colab
already provides it or container execution is simpler.

Connection is configured by `PostgresSettings` through the standard libpq
variables (`PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGPORT`; defaults
`127.0.0.1` / `osm_vn` / `postgres` / `postgres` / `5432`). The notebook
exports these values for compose and the shell scripts; manual shell runs must
export them as shown above.

| Table/View | Content |
|-----------|---------|
| `planet_osm_point` | POI nodes (amenity, tourism, shop, leisure) via `scripts/osm_poi.lua` |
| `pois` | View over `planet_osm_point` exposing `id, poi_name, amenity, tourism, shop, leisure, geometry, geo_wkt` |

The `geometry` column name is intentional: the upstream GS-QA schema and the
text2sql prompts hard-code `pois.geometry`.

---

## Step 2 — Question Generation

Datasets are versioned under `data/<version>/questions_vi/` with
`generator/questions_vi` as a symlink to the current version, so code and
notebooks keep using the familiar path. `data/` is **not tracked by git**
(`.gitignore`): the frozen dataset is published as a public GitHub Release
asset and restored by:

1. `./scripts/restore_dataset.sh` — downloads, unpacks, and sha256-verifies
   `data/v1.0.0/questions_vi` (idempotent; needs only `curl` + `unzip`), or
2. running the pipeline above against the **pinned snapshot** and regenerating
   with the pinned seed. `download_osm.sh` downloads the pinned
   `vietnam-260825.osm.pbf` snapshot:

   ```bash
   export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=osm_vn
   export PGUSER=postgres PGPASSWORD=postgres
   ./scripts/download_osm.sh
   ./scripts/init_database.sh && ./scripts/import_osm.sh
   # from the repo root (--output is resolved from the current directory):
   python generator/generator_vi.py --seed 42 --count 100 --output data/v1.0.0/questions_vi
   ```

   Regeneration needs the running database and the pinned PBF; the Release
   asset needs neither.

Either way, verify integrity against the sha256 table in
`docs/plans/T01-dataset-quality.md`. To publish a new version, generate into a
new directory, verify, update the MANIFEST, then repoint the symlink:

```bash
cd generator
python generator_vi.py --seed 42 --count 100 --output ../data/v1.0.1/questions_vi
# verify, update MANIFEST, then: ln -sfn ../data/v1.0.1/questions_vi questions_vi
```

The seed pins both the Python sampling and the per-call
`TABLESAMPLE ... REPEATABLE` seeds, so regeneration against the same imported
database is byte-identical (see the MANIFEST in the dataset directory).

### How It Works

Each question type follows a fixed SQL template. The generator:

1. Samples a random **anchor POI** from the database
2. Executes the SQL template against live data to get the ground-truth answer
3. Verifies the answer is non-empty and unambiguous
4. Fills a randomly chosen Vietnamese text template with the anchor name
5. Stores `{question, sql, answers, type, answer_type, question_entities}`

### Template Format (`templates_vi/*.txt`)

One question surface per line, with placeholders:

```text
Cho biết [1_type] gần [3] nhất là gì.
[1_type] nào gần [3] nhất hiện tại?
Bạn có biết [1_type] gần [3] nhất là gì không?
```

`[1]` = target POI category, `[2]` = distance/radius, `[3]` = anchor POI name.

---

## Step 3 — Quality Verification

```bash
python verify_vi.py --input questions_vi/ --spot-check 0.05 --seed 42
```

Automated checks (DB-free, per record):

- NFC normalization, no unreplaced `[N]` placeholders, plausible length
- Anchor POI excluded from its own answer set (SQL predicate + answer ids/geometries)
- No `LIMIT` without `ORDER BY` (nondeterministic answer subsets)
- Stable `{type}-NNN` id, record type matches the filename, no duplicate questions
- `question == question_surfaces.full`; Vietnamese surface consistency; name sanity

Stored answers are additionally re-executed against PostGIS at freeze time
(see the `validation` block in `questions_vi/MANIFEST.json`).

---

## Dataset Statistics

| Type | Answer type | N |
|------|------------|:-:|
| `knn+name` | POI name | 100 |
| `knn+loc` | Coordinates (lat/lon) | 100 |
| `knn+distance` | Distance in km | 100 |
| `knn:direction+name` | POI name | 100 |
| `range+name` | POI name | 100 |
| `range+loc` | Coordinates (lat/lon) | 100 |
| `range+count` | Integer count | 100 |
| `range:direction+name` | POI name | 100 |
| **Total** | | **800** |

---

## Output Format

Each `questions_vi/<type>.jsonl` — 100 lines, one JSON object per line:

```json
{
  "id": "knn+name-001",
  "question": "Bể bơi gần [anchor] nhất là gì?",
  "question_surfaces": {"full": "<question>", "stripped": "<diacritics-stripped>"},
  "type": "knn+name",
  "sql": "SELECT id, geo_wkt, poi_name FROM pois WHERE ... AND id <> <anchor> ORDER BY geometry <-> ... LIMIT 1",
  "answers": [
    {"id": 123, "poi_name": "[result name]", "geo_wkt": "POINT(106.xx 21.xx)"}
  ],
  "answer_type": "name",
  "question_entities": {"[1]": {"main_category": "...", "sub_category": "..."}, "[2]": {"poi_name": "[anchor]", "geo_wkt": "..."}}
}
```

List-type questions (`range+name`, `range+loc`, `range:direction+name`) store the
**full result set** ordered by distance to the anchor, with the anchor itself
excluded.

Field variations by type:

| Answer type | Key in `answers[]` | Format |
|-------------|-------------------|--------|
| name | `poi_name` | string |
| location | `geo_wkt` | WKT `POINT(lon lat)` |
| distance | `dist_km` | float (kilometres) |
| count | `count` | integer |
