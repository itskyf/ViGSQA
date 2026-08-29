"""
Vietnamese GS-QA generator — v2.0.0, all 28 canonical template types.

Families:
- POI family (20 types): {knn|range} x {plain|filter|direction|towards} with
  name/loc/angle/distance/count outputs. Upstream spatial semantics: ST_DWithin
  ranges, `<->` KNN, 8 azimuth sectors via degrees(ST_Azimuth(...)), towards
  corridors of ±22.5° around the anchor→second-POI azimuth.
- Intersects family (T11/T12/T24/T27/T28): region-anchored area/length/count.
- Multi-source (T7/T8) live in multisource_vi.py.

Vietnamese adaptations (documented in the v2.0.0 MANIFEST): regions are named
admin-boundary relations (VN has no postal-code boundaries); park/lake/road/
region display names come from native name columns, not Wikipedia; POI anchors
are always excluded from their own answer set (id <> anchor).
"""

import argparse
import json
import os
import random
import sys
import unicodedata

import psycopg
from tqdm import tqdm

from vigsqa.settings import PostgresSettings

DB_CONFIG = PostgresSettings().connection_kwargs()

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates_vi")
FILTER_LABELS_PATH = os.path.join(os.path.dirname(__file__), "filter_labels_vi.json")

# Give up on a template type after this many consecutive failed attempts.
MAX_CONSECUTIVE_FAILURES = 300

# ── TID ↔ type mapping (canonical GS-QA order) ──────────────────────────────
TID_MAP = {
    "T01": "range+name",
    "T02": "range:non_spat_filter+name",
    "T03": "range:direction+name",
    "T04": "range:towards+name",
    "T05": "knn+name",
    "T06": "knn:non_spat_filter+name",
    "T07": "knn+name+multi_source1",
    "T08": "knn+name+multi_source2",
    "T09": "knn:direction+name",
    "T10": "knn:towards+name",
    "T11": "intersects:area_max+name",
    "T12": "intersects:length_max+name",
    "T13": "range+loc",
    "T14": "range:non_spat_filter+loc",
    "T15": "range:direction+loc",
    "T16": "range:towards+loc",
    "T17": "knn+loc",
    "T18": "knn:non_spat_filter+loc",
    "T19": "knn:direction+loc",
    "T20": "knn:towards+loc",
    "T21": "range+angle",
    "T22": "knn+angle",
    "T23": "range+count",
    "T24": "intersects+count",
    "T25": "range+distance",
    "T26": "knn+distance",
    "T27": "intersects:area_total+area",
    "T28": "intersects:length_total+length",
}

# POI-family feature matrix: type -> (spatial, modifier, output).
POI_TYPE_FEATURES = {
    "range+name": ("range", "plain", "name"),
    "range:non_spat_filter+name": ("range", "filter", "name"),
    "range:direction+name": ("range", "direction", "name"),
    "range:towards+name": ("range", "towards", "name"),
    "knn+name": ("knn", "plain", "name"),
    "knn:non_spat_filter+name": ("knn", "filter", "name"),
    "knn:direction+name": ("knn", "direction", "name"),
    "knn:towards+name": ("knn", "towards", "name"),
    "range+loc": ("range", "plain", "loc"),
    "range:non_spat_filter+loc": ("range", "filter", "loc"),
    "range:direction+loc": ("range", "direction", "loc"),
    "range:towards+loc": ("range", "towards", "loc"),
    "knn+loc": ("knn", "plain", "loc"),
    "knn:non_spat_filter+loc": ("knn", "filter", "loc"),
    "knn:direction+loc": ("knn", "direction", "loc"),
    "knn:towards+loc": ("knn", "towards", "loc"),
    "range+angle": ("range", "plain", "angle"),
    "knn+angle": ("knn", "plain", "angle"),
    "range+count": ("range", "plain", "count"),
    "range+distance": ("range", "plain", "distance"),
    "knn+distance": ("knn", "plain", "distance"),
}

# ── Vietnamese POI label map ─────────────────────────────────────────────────
VN_LABEL = {
    # amenity
    "hospital": "bệnh viện",
    "clinic": "phòng khám",
    "pharmacy": "nhà thuốc",
    "school": "trường học",
    "university": "trường đại học",
    "bank": "ngân hàng",
    "restaurant": "nhà hàng",
    "cafe": "quán cà phê",
    "police": "đồn công an",
    "post_office": "bưu điện",
    "marketplace": "chợ",
    "place_of_worship": "cơ sở thờ tự",
    "fast_food": "quán ăn nhanh",
    # tourism
    "hotel": "khách sạn",
    "museum": "bảo tàng",
    "attraction": "điểm tham quan",
    "gallery": "phòng trưng bày",
    "hostel": "nhà nghỉ tập thể",
    # shop
    "supermarket": "siêu thị",
    "convenience": "cửa hàng tiện lợi",
    "bakery": "tiệm bánh",
    "electronics": "cửa hàng điện tử",
    # leisure
    "park": "công viên",
    "sports_centre": "trung tâm thể thao",
    "swimming_pool": "bể bơi",
    "stadium": "sân vận động",
    # water / waterway
    "lake": "hồ nước",
    "reservoir": "hồ chứa nước",
    "pond": "ao",
    "river": "sông",
    "canal": "kênh",
    # highway
    "motorway": "đường cao tốc",
    "trunk": "đường trục",
    "primary": "đường lớn",
    "secondary": "đường chính",
    "tertiary": "đường huyện",
    "residential": "đường dân cư",
    "unclassified": "đường nhỏ",
    "pedestrian": "đường đi bộ",
    "living_street": "đường nội bộ",
    "footway": "lối đi bộ",
    "cycleway": "đường xe đạp",
}

POIS_SELECTOR = {
    "amenity": [
        "hospital",
        "clinic",
        "pharmacy",
        "school",
        "university",
        "bank",
        "restaurant",
        "cafe",
        "police",
        "post_office",
        "marketplace",
        "place_of_worship",
        "fast_food",
    ],
    "tourism": ["hotel", "museum", "attraction", "gallery", "hostel"],
    "shop": ["supermarket", "convenience", "bakery", "electronics"],
    "leisure": ["park", "sports_centre", "swimming_pool", "stadium"],
}

# Intersects-family [1] selectors: (table, column, value, Vietnamese label).
AREA_SELECTOR = [
    ("parks", "leisure", "park", "công viên"),
    ("parks", "leisure", "garden", "vườn hoa"),
    ("parks", "leisure", "nature_reserve", "khu bảo tồn thiên nhiên"),
    ("lakes", "water", "lake", "hồ nước"),
    ("lakes", "water", "reservoir", "hồ chứa nước"),
    ("lakes", "water", "pond", "ao"),
]

LENGTH_SELECTOR = [
    ("roads", "highway", "primary", "đường lớn"),
    ("roads", "highway", "secondary", "đường chính"),
    ("roads", "highway", "tertiary", "đường nhánh"),
    ("roads", "highway", "residential", "đường dân cư"),
    ("roads", "highway", "motorway", "đường cao tốc"),
    ("roads", "highway", "trunk", "đường trục"),
    ("lakes", "waterway", "river", "sông"),
    ("lakes", "waterway", "canal", "kênh"),
]

# Upstream azimuth-sector semantics: 8 sectors of degrees(ST_Azimuth(anchor,
# target)), north centred on 0/360. Labels are Vietnamese compass words. The
# origin CTE aliases its column to `geom` so unqualified `geometry` references
# elsewhere in the statement resolve to `pois.geometry` unambiguously.
VN_DIRECTIONS = [
    (
        "bắc",
        "(degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 0.0 AND 22.5 "
        "OR degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 337.5 AND 360)",
    ),
    (
        "đông bắc",
        "degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 22.5 AND 67.5",
    ),
    ("đông", "degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 67.5 AND 112.5"),
    (
        "đông nam",
        "degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 112.5 AND 157.5",
    ),
    ("nam", "degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 157.5 AND 202.5"),
    (
        "tây nam",
        "degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 202.5 AND 247.5",
    ),
    ("tây", "degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 247.5 AND 292.5"),
    (
        "tây bắc",
        "degrees(ST_Azimuth(origin.geom, pois.geometry)) BETWEEN 292.5 AND 337.5",
    ),
]

RANGE_RADIUS_KM = [1, 2, 3, 5, 10, 20, 50]

# Sample random ref POI from the base table. REPEATABLE(x) makes the page sample
# deterministic for an unchanged table; the seed is drawn per call from the
# seeded Python RNG so the anchor sequence reproduces from --seed alone.
REF_SQL = """
    SELECT p.osm_id AS id,
           ST_AsText(ST_Transform(p.way,4326)) AS geo_wkt,
           ST_X(ST_Transform(p.way,4326)) AS lon,
           ST_Y(ST_Transform(p.way,4326)) AS lat,
           p.name AS poi_name,
           p.addr_city,
           p.amenity, p.tourism, p.shop, p.leisure
    FROM planet_osm_point p TABLESAMPLE SYSTEM(2) REPEATABLE({sample_seed})
    WHERE (p.amenity IS NOT NULL OR p.tourism IS NOT NULL
           OR p.shop IS NOT NULL OR p.leisure IS NOT NULL)
      AND p.name IS NOT NULL
    LIMIT 1;
"""

# Second POI for towards questions: a named POI of a different category within
# 100 km of the anchor (upstream `distance_limited` draw). The random OFFSET
# keeps determinism in Python while varying the chosen neighbour.
TOWARDS_REF_SQL = """
    SELECT p.osm_id AS id,
           ST_AsText(ST_Transform(p.way,4326)) AS geo_wkt,
           p.name AS poi_name,
           p.addr_city,
           p.amenity, p.tourism, p.shop, p.leisure
    FROM planet_osm_point p
    WHERE p.name IS NOT NULL
      AND (p.amenity IS NOT NULL OR p.tourism IS NOT NULL
           OR p.shop IS NOT NULL OR p.leisure IS NOT NULL)
      AND ST_DWithin(ST_Transform(p.way,4326)::geography,
                     ST_GeomFromText('{anchor_wkt}',4326)::geography, 100000)
    ORDER BY p.way <-> ST_Transform(ST_GeomFromText('{anchor_wkt}',4326),3857)
    LIMIT 1 OFFSET {offset};
"""

# Region anchoring the intersects family: admin boundaries (province=4,
# district=6, commune=8) containing the sampled POI.
REGION_SQL = """
    SELECT r.id, r.region_name, r.admin_level,
           ST_AsText(ST_Centroid(r.geometry::geometry)) AS geo_wkt
    FROM regions r
    WHERE ST_Intersects(r.geometry, ST_GeomFromText('{poi_wkt}',4326)::geography)
      AND r.admin_level IN ('4', '6', '8');
"""


# ── DB helpers ───────────────────────────────────────────────────────────────
def run_sql(sql: str) -> list[dict]:
    conn = psycopg.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {cols[j]: rows[i][j] for j in range(len(cols)) if rows[i][j] is not None}
        for i in range(len(rows))
    ]


def load_templates(name: str) -> list[str]:
    with open(os.path.join(TEMPLATE_DIR, f"{name}.txt"), encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_filter_labels() -> dict[str, list[list[str]]]:
    with open(FILTER_LABELS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Orthographic surfaces ────────────────────────────────────────────────────
def strip_diacritics(text: str) -> str:
    text = text.replace("Đ", "D").replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def surfaces(q: str) -> dict:
    q = nfc(q)
    return {"full": q, "stripped": strip_diacritics(q)}


def display_name(poi: dict) -> str:
    """Anchor surface: name plus city when OSM carries one (disambiguation)."""
    city = poi.get("addr_city")
    return f"{poi['poi_name']}, {nfc(city)}" if city else poi["poi_name"]


def poi_main_category(poi: dict) -> str | None:
    for cat in ("amenity", "tourism", "shop", "leisure"):
        if poi.get(cat):
            return cat
    return None


# ── Entity samplers ──────────────────────────────────────────────────────────
def get_ref() -> dict | None:
    try:
        rows = run_sql(REF_SQL.format(sample_seed=random.random()))
        if not rows:
            return None
        r = rows[0]
        if not r.get("geo_wkt") or not r.get("poi_name"):
            return None
        r["poi_name"] = nfc(r["poi_name"])
        return r
    except (psycopg.Error, KeyError, IndexError, TypeError):
        return None


def get_towards_ref(anchor: dict) -> dict | None:
    try:
        rows = run_sql(
            TOWARDS_REF_SQL.format(
                anchor_wkt=anchor["geo_wkt"], offset=random.randint(1, 20)
            )
        )
        if not rows:
            return None
        r = rows[0]
        if not r.get("geo_wkt") or not r.get("poi_name"):
            return None
        r["poi_name"] = nfc(r["poi_name"])
        return r
    except (psycopg.Error, KeyError, IndexError, TypeError):
        return None


def get_region(anchor: dict) -> dict | None:
    try:
        rows = run_sql(REGION_SQL.format(poi_wkt=anchor["geo_wkt"]))
        if not rows:
            return None
        r = random.choice(rows)
        r["region_name"] = nfc(r["region_name"])
        return r
    except (psycopg.Error, KeyError, IndexError, TypeError):
        return None


def pick_target_cat():
    main_cat = random.choice(list(POIS_SELECTOR.keys()))
    return main_cat, random.choice(POIS_SELECTOR[main_cat])


def pick_filter() -> dict:
    """Non-spatial filter draw: base category + attribute predicate + VN label."""
    labels = load_filter_labels()
    base_cat = random.choice(list(labels.keys()))
    label, predicate = random.choice(labels[base_cat])
    base_col = {
        "restaurant": "amenity",
        "cafe": "amenity",
        "museum": "tourism",
        "hospital": "amenity",
    }[base_cat]
    return {
        "base_cat": base_cat,
        "base_col": base_col,
        "label": label,
        "predicate": f"{base_col} ILIKE '{base_cat}' AND ({predicate})",
    }


def save(questions: list[dict], filename: str, output_dir: str):
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(q, ensure_ascii=False) + "\n" for q in questions)
    print(f"Saved {len(questions)} → {path}")


# ── POI family (T1-T6, T9, T10, T13-T26 minus multi-source/intersects) ─────
def generate_poi_type(type_str: str, tid: str, n: int = 100) -> list[dict]:
    spatial, modifier, output = POI_TYPE_FEATURES[type_str]
    tmpls = load_templates(type_str)
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc=f"{tid} {type_str}")
    while len(results) < n:
        if fails > MAX_CONSECUTIVE_FAILURES:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue

        # Category / filter selection for [1].
        if modifier == "filter":
            filt = pick_filter()
            cat_predicate, label = filt["predicate"], filt["label"]
            cat_entity = {
                "main_category": filt["base_col"],
                "sub_category": filt["base_cat"],
                "filter_label": filt["label"],
            }
            anchor_cat = poi_main_category(ref)
            if anchor_cat and ref.get(anchor_cat) == filt["base_cat"]:
                fails += 1
                continue
        else:
            main_cat, sub_cat = pick_target_cat()
            cat_predicate = f"{main_cat} ILIKE '{sub_cat}' AND poi_name IS NOT NULL"
            label = vn_label(sub_cat)
            cat_entity = {"main_category": main_cat, "sub_category": sub_cat}
            if poi_main_category(ref) == main_cat and ref.get(main_cat) == sub_cat:
                fails += 1
                continue

        anchor = display_name(ref)
        geom_4326 = f"ST_GeomFromText('{ref['geo_wkt']}',4326)"
        subst = {"[1]": label}

        # Modifier- and spatial-specific SQL fragments. Direction/towards run
        # against an `origin` CTE (upstream shape); plain/filter inline the
        # anchor literal like v1.0.0 did.
        direction = None
        towards = None
        if modifier == "direction":
            direction = random.choice(VN_DIRECTIONS)
        elif modifier == "towards":
            towards = get_towards_ref(ref)
            if not towards:
                fails += 1
                continue

        radius_km = 0
        if spatial == "range":
            radius_km = random.choice(RANGE_RADIUS_KM)
            subst["[2]"] = f"{radius_km} km"
            subst["[3]"] = anchor
        else:
            subst["[2]"] = anchor

        select_cols = "id, geo_wkt, poi_name"
        extra_select = ""
        if output == "distance":
            extra_select = (
                ", ST_Distance(geometry, origin.geom) AS distance"
                if modifier in ("direction", "towards")
                else f", ST_Distance(geometry, {geom_4326}::geography) AS distance"
            )
        elif output == "angle":
            extra_select = (
                ", degrees(ST_Azimuth(origin.geom, geometry)) AS angle"
                if modifier in ("direction", "towards")
                else f", degrees(ST_Azimuth({geom_4326}::geography, geometry)) AS angle"
            )
        elif output == "count":
            select_cols = "COUNT(*) AS count"

        entities = {"[1]": cat_entity}
        if spatial == "range":
            entities["[2]"] = {"distance": radius_km * 1000, "text": f"{radius_km} km"}
            anchor_key = "[3]"
        else:
            anchor_key = "[2]"
        entities[anchor_key] = {
            "poi_name": ref["poi_name"],
            "id": ref["id"],
            "geo_wkt": ref["geo_wkt"],
        }

        use_origin = modifier in ("direction", "towards")
        with_clause = ""
        from_clause = "FROM pois"
        anchor_geom_sql = "origin.geom"
        if use_origin:
            with_clause = f"WITH origin AS (SELECT {geom_4326}::geography AS geom)\n"
            from_clause = "FROM pois, origin"
            if modifier == "towards":
                towards_name = display_name(towards)
                towards_key = "[3]" if spatial == "knn" else "[4]"
                subst[towards_key] = towards_name
                entities[towards_key] = {
                    "poi_name": towards["poi_name"],
                    "id": towards["id"],
                    "geo_wkt": towards["geo_wkt"],
                }
                with_clause = (
                    f"WITH origin AS (SELECT {geom_4326}::geography AS geom),\n"
                    f"angle AS (SELECT degrees(ST_Azimuth(origin.geom, "
                    f"ST_GeomFromText('{towards['geo_wkt']}',4326)"
                    ")) AS value FROM origin)\n"
                )
                from_clause = "FROM pois, origin, angle"
        else:
            anchor_geom_sql = f"{geom_4326}::geography"

        where = [f"id <> {ref['id']}", cat_predicate]
        if towards is not None:
            # The described reference must not answer its own question either.
            where.append(f"id <> {towards['id']}")
        if spatial == "range":
            where.insert(
                0, f"ST_DWithin(geometry, {anchor_geom_sql}, {radius_km * 1000})"
            )
        if modifier == "direction":
            dir_label, dir_pred = direction
            where.append(dir_pred)
            dir_key = "[3]" if spatial == "knn" else "[4]"
            subst[dir_key] = dir_label
            entities[dir_key] = {"direction": dir_label}
        elif modifier == "towards":
            # Corridor of +/-22.5 degrees around the anchor->reference azimuth,
            # wrap-safe across 0/360: 382.5 = 360 + 22.5 keeps the dividend
            # positive (the azimuth difference never reaches -360), so the MOD
            # result is the minimal angular difference in [0, 360) and <= 45
            # selects the corridor. Plain BETWEEN -22.5/+22.5 silently drops
            # candidates whenever the reference azimuth crosses north.
            where.append(
                "MOD(degrees(ST_Azimuth(origin.geom, pois.geometry)) "
                "- angle.value + 382.5, 360) <= 45"
            )

        # COUNT aggregates cannot carry an ORDER BY over non-grouped columns;
        # every non-count query keeps a deterministic ORDER BY (LIMIT ⇒ ORDER).
        tail = ""
        if output != "count":
            tail = f"\nORDER BY geometry <-> {anchor_geom_sql}"
            if spatial == "knn":
                tail += " LIMIT 1"
        sql = (
            f"{with_clause}SELECT {select_cols}{extra_select}\n{from_clause}\n"
            f"WHERE {' AND '.join(where)}{tail};"
        )

        try:
            rows = run_sql(sql)
        except (psycopg.Error, IndexError, KeyError) as e:
            # A composing bug must not die silently after 300 failed draws.
            print(f"SQL error ({type_str}): {e}", file=sys.stderr)
            fails += 1
            continue

        if output == "count":
            count = rows[0].get("count", 0) if rows else 0
            if count == 0:
                fails += 1
                continue
            answers = [{"count": count}]
        else:
            if not rows:
                fails += 1
                continue
            if output == "distance":
                answers = [
                    {
                        "id": r.get("id"),
                        "geo_wkt": r.get("geo_wkt"),
                        "poi_name": r.get("poi_name"),
                        "distance": round(float(r["distance"]), 2),
                    }
                    for r in rows
                ]
            elif output == "angle":
                answers = [
                    {
                        "id": r.get("id"),
                        "geo_wkt": r.get("geo_wkt"),
                        "poi_name": r.get("poi_name"),
                        # % 360 after rounding: 359.96 must not round up to 360
                        # (azimuths are [0,360); 360 would break angle errors).
                        "angle": round(float(r["angle"]), 1) % 360,
                    }
                    for r in rows
                ]
            else:
                answers = rows

        fails = 0
        q = nfc(random.choice(tmpls))
        for key, value in subst.items():
            q = q.replace(key, value)
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": answers,
                "answer_type": output,
                "id": f"{type_str}-{len(results) + 1:03d}",
                "tid": tid,
                "type": type_str,
                "question_entities": entities,
            }
        )
        pbar.update(1)
    pbar.close()
    return results


# ── Intersects family (T11/T12/T24/T27/T28) ─────────────────────────────────
def generate_intersects_type(type_str: str, tid: str, n: int = 100) -> list[dict]:
    # "intersects:area_max+name" -> "area_max"; "intersects+count" -> "count"
    kind = type_str.removeprefix("intersects").lstrip(":+").split("+")[0]
    tmpls = load_templates(type_str)
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc=f"{tid} {type_str}")
    while len(results) < n:
        if fails > MAX_CONSECUTIVE_FAILURES:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        region = get_region(ref)
        if not region:
            fails += 1
            continue
        region_subquery = f"(SELECT geometry FROM regions WHERE id = {region['id']})"

        if kind == "count":
            main_cat, sub_cat = pick_target_cat()
            label = vn_label(sub_cat)
            table, predicate = "pois", f"{main_cat} ILIKE '{sub_cat}'"
            entity = {"table": "pois", "column": main_cat, "value": sub_cat}
            sql = (
                f"SELECT COUNT(*) AS count FROM pois\n"
                f"WHERE {predicate}\n"
                f"  AND ST_Intersects(geometry, {region_subquery});"
            )
            try:
                rows = run_sql(sql)
            except psycopg.Error as e:
                print(f"SQL error ({type_str}): {e}", file=sys.stderr)
                fails += 1
                continue
            count = rows[0].get("count", 0) if rows else 0
            if count == 0:
                fails += 1
                continue
            answers = [{"count": count}]
        else:
            if kind in ("area_max", "area_total"):
                table, column, value, label = random.choice(AREA_SELECTOR)
                measure = "ST_Area(geometry)"
            else:
                table, column, value, label = random.choice(LENGTH_SELECTOR)
                measure = "ST_Length(geometry)"
            name_col = {
                "parks": "park_name",
                "lakes": "lake_name",
                "roads": "road_name",
            }[table]
            predicate = f"{column} ILIKE '{value}'"
            entity = {"table": table, "column": column, "value": value}
            if kind == "area_max":
                sql = (
                    f"SELECT id, geo_wkt, {name_col}, {measure} AS area\n"
                    f"FROM {table}\n"
                    f"WHERE {predicate}\n"
                    f"  AND ST_Intersects(geometry, {region_subquery})\n"
                    f"ORDER BY area DESC\nLIMIT 1;"
                )
            elif kind == "length_max":
                sql = (
                    f"SELECT id, geo_wkt, {name_col}, {measure} AS length\n"
                    f"FROM {table}\n"
                    f"WHERE {predicate}\n"
                    f"  AND ST_Intersects(geometry, {region_subquery})\n"
                    f"ORDER BY length DESC\nLIMIT 1;"
                )
            else:  # area_total / length_total
                sql = (
                    f"SELECT SUM({measure}) AS {kind.split('_')[0]}\n"
                    f"FROM {table}\n"
                    f"WHERE {predicate}\n"
                    f"  AND ST_Intersects(geometry, {region_subquery});"
                )
            try:
                rows = run_sql(sql)
            except psycopg.Error as e:
                print(f"SQL error ({type_str}): {e}", file=sys.stderr)
                fails += 1
                continue
            if not rows:
                fails += 1
                continue
            if kind in ("area_max", "length_max"):
                if not rows[0].get(name_col):
                    fails += 1
                    continue
                answers = rows
            else:
                total = rows[0].get(kind.split("_")[0])
                if not total or float(total) <= 0:
                    fails += 1
                    continue
                answers = [{kind.split("_")[0]: round(float(total), 2)}]

        fails = 0
        q = nfc(
            random.choice(tmpls)
            .replace("[1]", label)
            .replace("[2]", region["region_name"])
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        answer_type = {
            "count": "count",
            "area_max": "name",
            "length_max": "name",
            "area_total": "area",
            "length_total": "length",
        }[kind]
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": answers,
                "answer_type": answer_type,
                "id": f"{type_str}-{len(results) + 1:03d}",
                "tid": tid,
                "type": type_str,
                "question_entities": {
                    "[1]": entity,
                    "[2]": {
                        "region_name": region["region_name"],
                        "id": region["id"],
                        "admin_level": region["admin_level"],
                        "geo_wkt": region["geo_wkt"],
                    },
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def main() -> None:
    """Generate all 28 VN-GeoQA v2.0.0 types from the `osm_vn` database."""
    parser = argparse.ArgumentParser(
        description="Generate VN-GeoQA v2.0.0 benchmark questions from PostGIS."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="seeds Python choices and per-call TABLESAMPLE REPEATABLE seeds",
    )
    parser.add_argument("--count", type=int, default=100, help="questions per type")
    parser.add_argument("--output", default="questions_vi", help="output directory")
    parser.add_argument(
        "--types",
        default=None,
        help="comma-separated TIDs to generate (default: all 28, e.g. T01,T07)",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    os.makedirs(args.output, exist_ok=True)
    # Only clear question files so provenance sidecars (e.g. MANIFEST.json) survive.
    for f in os.listdir(args.output):
        if f.endswith(".jsonl"):
            os.remove(os.path.join(args.output, f))

    tids = args.types.split(",") if args.types else list(TID_MAP)
    total = 0
    for tid in tids:
        type_str = TID_MAP[tid]
        if type_str in POI_TYPE_FEATURES:
            qs = generate_poi_type(type_str, tid, args.count)
        elif type_str.startswith("intersects"):
            qs = generate_intersects_type(type_str, tid, args.count)
        elif type_str == "knn+name+multi_source1":
            # Function-local: multisource_vi imports this module's helpers, so
            # a top-level import would be circular.
            from multisource_vi import generate_multi_source1  # noqa: PLC0415

            qs = generate_multi_source1(tid, args.count)
        elif type_str == "knn+name+multi_source2":
            from multisource_vi import generate_multi_source2  # noqa: PLC0415

            qs = generate_multi_source2(tid, args.count)
        else:
            raise ValueError(f"no generator for {type_str}")
        save(qs, f"{type_str}.jsonl", args.output)
        total += len(qs)
    print(f"\nTotal: {total} questions across {len(tids)} template types")


def vn_label(sub_cat: str) -> str:
    return VN_LABEL.get(sub_cat, sub_cat.replace("_", " "))


if __name__ == "__main__":
    main()
