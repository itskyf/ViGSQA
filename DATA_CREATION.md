# VN-GeoQA: Vietnamese Geospatial QA Data Creation

## Overview

VN-GeoQA is a Vietnamese geospatial question-answering benchmark derived from OpenStreetMap (OSM) data for Vietnam. It adapts the GS-QA pipeline (arXiv 2605.22811) to generate spatially grounded questions with verifiable SQL answers over a PostGIS database.

**Final dataset:** 800 questions × 8 template types, all in Vietnamese, all SQL-verified.

---

## Data Pipeline

### Step 1: OSM Data Acquisition

Downloaded Vietnam OSM extract from Geofabrik:

```text
vietnam-latest.osm.pbf  (~312 MB)
```

Geofabrik does not provide sub-region extracts for Vietnam, so the full national extract was used.

### Step 2: PostGIS Database Setup

Ran PostGIS 15 via Docker:

```bash
docker run -d --name postgis_vn \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=osm_vn \
  -p 5432:5432 \
  postgis/postgis:15-3.4
```

### Step 3: OSM Data Loading

Loaded the PBF into PostgreSQL using osm2pgsql (via Docker):

```bash
docker run --rm --network host \
  -v /path/to/vietnam-latest.osm.pbf:/data/vietnam.osm.pbf \
  iboates/osm2pgsql \
  osm2pgsql --hstore --slim -d osm_vn \
    -H localhost -U postgres \
    /data/vietnam.osm.pbf
```

osm2pgsql creates these tables with SRID 3857 (Web Mercator):

| Table | Contents |
|---|---|
| `planet_osm_point` | POI nodes |
| `planet_osm_line` | Roads, rivers, etc. |
| `planet_osm_polygon` | Parks, lakes, buildings, etc. |

The `--hstore` flag stores extra tags in a `tags` hstore column; core tags (`amenity`, `tourism`, `shop`, `leisure`, etc.) get dedicated columns.

### Step 4: PostGIS Views

Created convenience views with SRID 4326 (WGS84) for geography operations:

```sql
CREATE VIEW pois AS
SELECT osm_id AS id,
    ST_Transform(way, 4326)::geography AS geometry,
    ST_AsText(ST_Transform(way, 4326)) AS geo_wkt,
    name AS poi_name,
    amenity, tourism, shop, leisure,
    tags->'cuisine' AS cuisine,
    operator, tags->'wikidata' AS wikidata
FROM planet_osm_point
WHERE (amenity IS NOT NULL OR tourism IS NOT NULL
       OR shop IS NOT NULL OR leisure IS NOT NULL)
  AND name IS NOT NULL;
```

Key issue: `planet_osm_point.way` is SRID 3857. All geography operations require `ST_Transform(way, 4326)::geography`. Direct cast of SRID 3857 to geography fails with `InvalidParameterValue`.

### Step 5: Vietnamese Template Translation

Translated all 26 GS-QA template types into Vietnamese, stored in `generator/templates_vi/*.txt`. Each file contains 20–30 paraphrase variants per template type. Placeholders use `[1]`, `[2]`, `[3]`, `[4]`.

Example (`knn+name.txt`):

```text
[1] nào gần [2] nhất?
[1] gần nhất với [2] là gì?
Tìm [1] gần [2] nhất giúp tôi với.
Bạn có thể gợi ý [1] gần [2] nhất không?
```

### Step 6: Vietnamese POI Label Mapping

Built `VN_LABEL` dict in `generator_vi.py` mapping OSM category keys to Vietnamese:

| OSM key | Vietnamese label |
|---|---|
| `hospital` | bệnh viện |
| `clinic` | phòng khám |
| `university` | trường đại học |
| `restaurant` | nhà hàng |
| `cafe` | quán cà phê |
| `hotel` | khách sạn |
| `museum` | bảo tàng |
| `supermarket` | siêu thị |
| `park` | công viên |
| `swimming_pool` | bể bơi |
| `stadium` | sân vận động |
| ... (34 total) | ... |

### Step 7: Question Generation (`generator/generator_vi.py`)

Generator implements 8 spatial query types:

| Template type | Query pattern | Answer type |
|---|---|---|
| `knn+name` | Nearest POI of category X to reference POI Y | name |
| `knn+loc` | Nearest POI of category X to reference POI Y | location (WKT) |
| `knn+distance` | Distance to nearest POI of category X from Y | distance (km) |
| `knn:direction+name` | Nearest POI of category X in direction D from Y | name |
| `range+name` | POIs of category X within radius R of Y | name(s) |
| `range+loc` | POIs of category X within radius R of Y | location(s) |
| `range+count` | Count of POIs of category X within radius R of Y | count |
| `range:direction+name` | POIs of category X within radius R in direction D from Y | name(s) |

**Reference POI sampling:** Uses `TABLESAMPLE SYSTEM(2)` on `planet_osm_point` base table directly — `TABLESAMPLE` cannot be applied to views or materialized views.

**KNN operator:** Uses PostGIS `<->` KNN operator on SRID 3857 geometry for ordering, then converts results to WGS84:

```sql
ORDER BY p.way <-> ST_Transform(ST_GeomFromText(ref_wkt, 4326), 3857)
```

**Range queries:** Use `ST_DWithin` with `::geography` cast for metre-accurate distance:

```sql
ST_DWithin(geometry, ST_GeomFromText(ref_wkt, 4326)::geography, radius_m)
```

**Direction predicates:** Computed from lat/lon of reference POI:

| Direction | SQL predicate |
|---|---|
| bắc (N) | `ST_Y(ST_Transform(way,4326)) > {lat}` |
| nam (S) | `ST_Y(ST_Transform(way,4326)) < {lat}` |
| đông (E) | `ST_X(ST_Transform(way,4326)) > {lon}` |
| tây (W) | `ST_X(ST_Transform(way,4326)) < {lon}` |
| đông bắc (NE) | Y > lat AND X > lon |
| tây bắc (NW) | Y > lat AND X < lon |
| đông nam (SE) | Y < lat AND X > lon |
| tây nam (SW) | Y < lat AND X < lon |

**Text normalization:**

- All OSM names fetched from DB are NFC-normalized before insertion into templates
- `strip_diacritics()` generates a diacritic-free surface form for search/indexing — handles `Đ/đ` explicitly since NFKD decomposition does not strip them

### Step 8: Verification (`generator/verify_vi.py`)

Three-layer verification:

**Layer 1 — SQL execution** (automatic during generation): Every SQL in every record was executed against the live PostGIS DB to produce the answer. Answers are not heuristic — they are the actual DB result.

**Layer 2 — Automated text checks per record:**

- Question string is NFC-normalized
- No unreplaced placeholders (`[1]`, `[2]`, etc.) remain
- Question length between 10 and 300 characters
- OSM name appears verbatim in question (encoding sanity)
- SQL contains expected spatial keywords (`ST_`, `ORDER BY`, `LIMIT` or `COUNT`)

**Layer 3 — Human spot-check TSV:** 5% sample printed as tab-separated table with `question`, `expected_answer`, and blank `annotation` column for manual review.

```text
python3 verify_vi.py --input questions_vi/ --spot-check 0.05
```

#### Result: 800/800 passed (100%)

---

## Output Format

Each line in `generator/questions_vi/*.jsonl` is a JSON object:

```json
{
  "question": "Cho biết bể bơi gần <REF_POI_NAME> nhất là gì.",
  "question_surfaces": {
    "full": "Cho biết bể bơi gần <REF_POI_NAME> nhất là gì.",
    "stripped": "Cho biet be boi gan <REF_POI_NAME> nhat la gi."
  },
  "sql": "SELECT id, geo_wkt, poi_name FROM pois WHERE leisure ILIKE 'swimming_pool' ...",
  "answers": [
    {
      "id": 1234567890,
      "geo_wkt": "POINT(105.xxx 21.xxx)",
      "poi_name": "<ANSWER_POI_NAME>"
    }
  ],
  "answer_type": "name",
  "type": "knn+name",
  "question_entities": {
    "[1]": {"main_category": "leisure", "sub_category": "swimming_pool"},
    "[2]": {"poi_name": "<REF_POI_NAME>", "geo_wkt": "POINT(106.xxx 22.xxx)"}
  }
}
```

`answer_type` values: `name` | `loc` | `distance` | `count`

---

## Dataset Statistics

| File | Template type | Count |
|---|---|---|
| `knn+name.jsonl` | KNN → name | 100 |
| `knn+loc.jsonl` | KNN → location | 100 |
| `knn+distance.jsonl` | KNN → distance | 100 |
| `knn:direction+name.jsonl` | directional KNN → name | 100 |
| `range+name.jsonl` | range → name(s) | 100 |
| `range+loc.jsonl` | range → location(s) | 100 |
| `range+count.jsonl` | range → count | 100 |
| `range:direction+name.jsonl` | directional range → name(s) | 100 |
| **Total** | | **800** |

---

## Key Technical Decisions

| Decision | Reason |
|---|---|
| SRID 3857 → 4326 transform everywhere | `planet_osm_point.way` stored in Web Mercator; `::geography` cast requires WGS84 |
| `TABLESAMPLE` on base table, not view | PostgreSQL only allows `TABLESAMPLE` on tables and materialized views |
| `Đ/đ` handled before NFKD | NFKD does not decompose Vietnamese Đ/đ; explicit replace required |
| NFC on all OSM names | Some OSM names stored in non-NFC form; normalize before template fill |
| Docker for PostGIS + osm2pgsql | No native sudo/apt access; avoids system-level installation |

---

## Files

```text
GS-QA/
├── DATA_CREATION.md             # This document
└── generator/
    ├── generator_vi.py          # Main generation script (8 generators)
    ├── verify_vi.py             # 3-layer verification script
    ├── templates_vi/            # Vietnamese question templates (26 types)
    │   ├── knn+name.txt
    │   ├── knn+loc.txt
    │   ├── knn+distance.txt
    │   ├── knn:direction+name.txt
    │   ├── range+name.txt
    │   ├── range+loc.txt
    │   ├── range+count.txt
    │   ├── range:direction+name.txt
    │   └── ... (18 more template types, not yet wired to generators)
    └── questions_vi/            # Generated output (800 records)
        ├── knn+name.jsonl
        ├── knn+loc.jsonl
        ├── knn+distance.jsonl
        ├── knn:direction+name.jsonl
        ├── range+name.jsonl
        ├── range+loc.jsonl
        ├── range+count.jsonl
        └── range:direction+name.jsonl
```
