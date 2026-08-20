# Data Generation — VN-GeoQA

## Overview

VN-GeoQA contains 800 Vietnamese geospatial questions generated automatically from OpenStreetMap Vietnam data stored in a PostGIS database. Questions are paired with ground-truth SQL queries and answers verified against the live database.

---

## Pipeline

```
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

```bash
bash setup_vn.sh
```

Downloads Vietnam OSM data (~100 MB) from Geofabrik and loads into PostGIS:

| Table/View | Content |
|-----------|---------|
| `pois` | Points of interest (amenity, tourism, shop, leisure) |
| `roads` | Named roads and highways |
| `parks` | Parks, gardens, nature reserves |
| `lakes` | Water bodies and waterways |

Default DB params: `host=localhost dbname=osm_vn user=postgres password=postgres port=5432`

---

## Step 2 — Question Generation

```bash
cd generator
python generator_vi.py --output questions_vi/ --count 100
```

### How It Works

Each question type follows a fixed SQL template. The generator:

1. Samples a random **anchor POI** from the database
2. Executes the SQL template against live data to get the ground-truth answer
3. Verifies the answer is non-empty and unambiguous
4. Fills a randomly chosen Vietnamese text template with the anchor name
5. Stores `{question, sql, answers, type, answer_type, question_entities}`

### Template Format (`templates_vi/*.txt`)

One question surface per line, with placeholders:

```
Cho biết [1_type] gần [3] nhất là gì.
[1_type] nào gần [3] nhất hiện tại?
Bạn có biết [1_type] gần [3] nhất là gì không?
```

`[1]` = target POI category, `[2]` = distance/radius, `[3]` = anchor POI name.

---

## Step 3 — Quality Verification

```bash
python verify_vi.py --input questions_vi/ --spot-check 0.05
```

Checks:
- Answer exists in DB (re-executes SQL)
- Question contains Vietnamese characters and is plausible length
- No duplicate questions within a type
- Coordinates within Vietnam bounding box (lat 8–24, lon 100–110)

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
  "question": "Bể bơi gần [anchor] nhất là gì?",
  "type": "knn+name",
  "sql": "SELECT poi_name, geo_wkt FROM pois ORDER BY geometry <-> (...) LIMIT 1",
  "answers": [
    {"poi_name": "[result name]", "geo_wkt": "POINT(106.xx 21.xx)"}
  ],
  "answer_type": "name",
  "question_entities": ["[anchor]"]
}
```

Field variations by type:

| Answer type | Key in `answers[]` | Format |
|-------------|-------------------|--------|
| name | `poi_name` | string |
| location | `geo_wkt` | WKT `POINT(lon lat)` |
| distance | `dist_km` | float (kilometres) |
| count | `count` | integer |
