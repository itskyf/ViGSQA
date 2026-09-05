# VN-GeoQA Dataset Generation

VN-GeoQA is the Vietnamese dataset produced by ViGSQA from OpenStreetMap data stored in PostgreSQL/PostGIS.
Version `v3.0.0` contains 2,800 questions: 100 questions for each of the 28 canonical GS-QA types.
Each record includes a Vietnamese question, the SQL query used to compute its answer, the resulting answer data, and structured question metadata.

This is the single reference for restoring, generating, and verifying the dataset.
For the complete course workflow, see the repository [README](../README.md).

## Restore the course dataset

The recommended course path uses `vn-geoqa.zip` from the [v3.0.0 release](https://github.com/itskyf/ViGSQA/releases/tag/v3.0.0):

```bash
./scripts/restore_dataset.sh
```

The script downloads the archive when necessary, extracts it to `data/questions_vi`, and verifies every JSONL file against `scripts/v3.0.0.sha256`.
The repository reads the restored files through the `generator/questions_vi` symlink.
Files under `data/` are intentionally excluded from Git.

The course notebook also restores `osm-vn.dump`, so it does not need to download or import the raw OSM snapshot.

## Generation pipeline

The implementation is organized as follows:

```text
vietnam-260901.osm.pbf
        │
        ▼
osm2pgsql + scripts/osm_poi.lua
        │
        ▼
PostgreSQL/PostGIS (osm_vn)
        │
        ▼
generator/generator_vi.py
        │
        ▼
28 JSONL files
        │
        ▼
generator/verify_vi.py
```

The pinned source is the Geofabrik snapshot `vietnam-260901.osm.pbf` with SHA-256 `edf2d41d93b25474acc14a34f6c313940ecfea5671835299ddd793c60d08a3e8`.
`scripts/download_osm.sh` downloads and verifies this exact snapshot.
`scripts/import_osm.sh` imports it with the repository's osm2pgsql configuration and creates the reference views used by the generator.

The main reference views are `pois`, `regions`, `parks`, `lakes`, and `roads`.
Geometry is exposed in WGS84 through `geometry` and `geo_wkt` fields so generated SQL can use PostGIS geography operations consistently.

## Generate the dataset

Install the project, enter its environment, and configure the local database:

```bash
pixi install
pixi shell
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=osm_vn
export PGUSER=postgres PGPASSWORD=postgres
```

To rebuild the database from the pinned PBF instead of restoring `osm-vn.dump`:

```bash
DB_RESTORE=0 ./scripts/bootstrap_postgres.sh
```

Generate into a staging directory so the course dataset at `data/questions_vi` remains unchanged:

```bash
python generator/generator_vi.py \
  --seed 42 \
  --count 100 \
  --output data/rebuild/questions_vi
```

Use `--types T01,T07` to generate only selected question types during development.
The seed controls Python sampling and the repeatable PostgreSQL samples used by the generator.

For each question, `generator/generator_vi.py` selects real entities, fills a Vietnamese template, executes the corresponding SQL, rejects unusable results, and stores the verified answer.
T7 and T8 add external Wikipedia facts through `generator/multisource_vi.py` while keeping those answer attributes outside the Text2SQL schema.

## Verify generated questions

Run all automated checks on the staging output:

```bash
python generator/verify_vi.py \
  --input data/rebuild/questions_vi \
  --all \
  --spot-check 0.05 \
  --seed 42
```

The verifier checks identifiers, question types, answer types, required fields, Vietnamese normalization, unreplaced template tokens, duplicate questions, SQL ordering, anchor exclusion, numeric answer validity, location addresses, and the T7/T8 out-of-schema rule.
The optional spot check prints a deterministic TSV sample for human review.

The `v3.0.0` release was produced with all 2,800 records passing these checks and a byte-identical seed-42 regeneration.

## Dataset contract

| Property | Value |
|---|---|
| Version | `v3.0.0` |
| Questions | 2,800 |
| GS-QA types | 28 (`T01`–`T28`) |
| Questions per type | 100 |
| Seed | 42 |
| Output | One JSONL file per question type |

Answer types are distributed as follows:

| Answer type | Questions | Stored value |
|---|---:|---|
| `name` | 1,200 | Entity name or distance-ordered name list |
| `loc` | 800 | Canonical address, native OSM address fields, and `geo_wkt` |
| `angle` | 200 | Degrees clockwise from north |
| `count` | 200 | Integer count |
| `distance` | 200 | Metres |
| `area` | 100 | Square metres |
| `length` | 100 | Metres |

Location answers use `geo_wkt` as the spatial reference and derive their address text only from the stored native OSM address fields.
Range questions store the complete result set in distance order rather than an arbitrary subset.
T7 and T8 retain their external facts in the question records rather than exposing them as columns in the reference database.

## Record format

Each line of a JSONL file is one object with this shape:

```json
{
  "id": "intersects+count-001",
  "tid": "T24",
  "type": "intersects+count",
  "question": "Đếm số cửa hàng điện tử nằm trong Thành phố Hồ Chí Minh.",
  "question_surfaces": {
    "full": "Đếm số cửa hàng điện tử nằm trong Thành phố Hồ Chí Minh.",
    "stripped": "Dem so cua hang dien tu nam trong Thanh pho Ho Chi Minh."
  },
  "sql": "SELECT COUNT(*) AS count FROM pois WHERE ...;",
  "answers": [{"count": 51}],
  "answer_type": "count",
  "question_entities": {
    "[1]": {"table": "pois", "column": "shop", "value": "electronics"},
    "[2]": {"region_name": "Thành phố Hồ Chí Minh", "id": 1973756}
  }
}
```

The dataset manifest records the complete `tid`-to-type mapping, source information, file counts, and validation summary.

## Relevant implementation

| Path | Purpose |
|---|---|
| `generator/generator_vi.py` | Generate all 28 Vietnamese question types |
| `generator/verify_vi.py` | Validate generated JSONL records |
| `generator/templates_vi/` | Store Vietnamese question templates |
| `generator/multisource_vi.py` | Generate T7/T8 external-fact questions |
| `scripts/download_osm.sh` | Download and verify the pinned OSM snapshot |
| `scripts/import_osm.sh` | Import OSM data into PostGIS |
| `scripts/osm_poi.lua` | Configure the osm2pgsql POI import |
| `sql/refresh_views.sql` | Define the reference database views |
| `scripts/restore_dataset.sh` | Restore the `v3.0.0` course dataset |
