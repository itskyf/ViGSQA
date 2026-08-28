"""
Vietnamese GeoQA generator — VN-GeoQA benchmark data generation.
Covers: knn+name, knn+loc, knn+distance, knn:direction+name,
        range+name, range+loc, range+count, range:direction+name
"""

import argparse
import json
import os
import random
import unicodedata

import psycopg2
from tqdm import tqdm

DB_CONFIG = {
    "host": os.getenv("PGHOST", "127.0.0.1"),
    "dbname": os.getenv("PGDATABASE", "osm_vn"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
    "port": int(os.getenv("PGPORT", "5432")),
}

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates_vi")

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
    "place_of_worship": "cơ sở tôn giáo",
    "fast_food": "quán ăn nhanh",
    "fuel": "trạm xăng",
    "atm": "cây ATM",
    "parking": "bãi đỗ xe",
    # tourism
    "hotel": "khách sạn",
    "museum": "bảo tàng",
    "attraction": "điểm tham quan",
    "gallery": "phòng triển lãm",
    "hostel": "nhà nghỉ",
    "resort": "khu nghỉ dưỡng",
    "guest_house": "nhà khách",
    "motel": "nhà nghỉ",
    # shop
    "supermarket": "siêu thị",
    "convenience": "cửa hàng tiện lợi",
    "bakery": "tiệm bánh",
    "electronics": "cửa hàng điện tử",
    "clothes": "cửa hàng quần áo",
    # leisure
    "park": "công viên",
    "sports_centre": "trung tâm thể thao",
    "swimming_pool": "bể bơi",
    "stadium": "sân vận động",
    # highway
    "primary": "đường chính",
    "secondary": "đường phụ",
    "tertiary": "đường nhánh",
    "residential": "đường dân cư",
}


def vn_label(sub_cat: str) -> str:
    return VN_LABEL.get(sub_cat, sub_cat.replace("_", " "))


# ── Direction labels ─────────────────────────────────────────────────────────
DIRECTIONS = [
    ("bắc", "ST_Y(ST_Transform(way,4326)) > {lat}"),
    ("nam", "ST_Y(ST_Transform(way,4326)) < {lat}"),
    ("đông", "ST_X(ST_Transform(way,4326)) > {lon}"),
    ("tây", "ST_X(ST_Transform(way,4326)) < {lon}"),
    (
        "đông bắc",
        "ST_Y(ST_Transform(way,4326)) > {lat} AND ST_X(ST_Transform(way,4326)) > {lon}",
    ),
    (
        "tây bắc",
        "ST_Y(ST_Transform(way,4326)) > {lat} AND ST_X(ST_Transform(way,4326)) < {lon}",
    ),
    (
        "đông nam",
        "ST_Y(ST_Transform(way,4326)) < {lat} AND ST_X(ST_Transform(way,4326)) > {lon}",
    ),
    (
        "tây nam",
        "ST_Y(ST_Transform(way,4326)) < {lat} AND ST_X(ST_Transform(way,4326)) < {lon}",
    ),
]

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

# Sample random ref POI from base table. REPEATABLE(x) makes the page sample
# deterministic for an unchanged table; the seed is drawn per call from the
# seeded Python RNG so the anchor sequence reproduces from --seed alone.
REF_SQL = """
    SELECT p.osm_id AS id,
           ST_AsText(ST_Transform(p.way,4326)) AS geo_wkt,
           ST_X(ST_Transform(p.way,4326)) AS lon,
           ST_Y(ST_Transform(p.way,4326)) AS lat,
           p.name AS poi_name,
           p.amenity, p.tourism, p.shop, p.leisure
    FROM planet_osm_point p TABLESAMPLE SYSTEM(2) REPEATABLE({sample_seed})
    WHERE (p.amenity IS NOT NULL OR p.tourism IS NOT NULL
           OR p.shop IS NOT NULL OR p.leisure IS NOT NULL)
      AND p.name IS NOT NULL
    LIMIT 1;
"""


# ── DB helpers ───────────────────────────────────────────────────────────────
def run_sql(sql: str) -> list[dict]:
    conn = psycopg2.connect(**DB_CONFIG)
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
        return [l.strip() for l in f if l.strip()]


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


# ── Common loop helper ───────────────────────────────────────────────────────
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
    except (psycopg2.Error, KeyError, IndexError, TypeError):
        return None


def pick_target_cat():
    main_cat = random.choice(list(POIS_SELECTOR.keys()))
    return main_cat, random.choice(POIS_SELECTOR[main_cat])


def save(questions: list[dict], filename: str, output_dir: str):
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(q, ensure_ascii=False) + "\n" for q in questions)
    print(f"Saved {len(questions)} → {path}")


# ── Generator functions ───────────────────────────────────────────────────────


def generate_knn_name(n=100) -> list[dict]:
    tmpls = load_templates("knn+name")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="knn+name")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        sql = f"""SELECT id, geo_wkt, poi_name FROM pois
            WHERE {main_cat} ILIKE '{sub_cat}' AND poi_name IS NOT NULL AND id <> {ref["id"]}
            ORDER BY geometry <-> ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography LIMIT 1;"""
        try:
            targets = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        if not targets:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls).replace("[1]", label).replace("[2]", ref["poi_name"])
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": [targets[0]],
                "answer_type": "name",
                "id": f"knn+name-{len(results) + 1:03d}",
                "type": "knn+name",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def generate_knn_loc(n=100) -> list[dict]:
    tmpls = load_templates("knn+loc")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="knn+loc")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        sql = f"""SELECT id, geo_wkt, poi_name FROM pois
            WHERE {main_cat} ILIKE '{sub_cat}' AND poi_name IS NOT NULL AND id <> {ref["id"]}
            ORDER BY geometry <-> ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography LIMIT 1;"""
        try:
            targets = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        if not targets:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls).replace("[1]", label).replace("[2]", ref["poi_name"])
        )
        ans = targets[0]
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": [ans],
                "answer_type": "loc",
                "id": f"knn+loc-{len(results) + 1:03d}",
                "type": "knn+loc",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def generate_knn_distance(n=100) -> list[dict]:
    tmpls = load_templates("knn+distance")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="knn+distance")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        sql = f"""SELECT id, geo_wkt, poi_name,
            ST_Distance(geometry, ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography) AS dist_m
            FROM pois
            WHERE {main_cat} ILIKE '{sub_cat}' AND poi_name IS NOT NULL AND id <> {ref["id"]}
            ORDER BY geometry <-> ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography LIMIT 1;"""
        try:
            targets = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        if not targets:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls).replace("[1]", label).replace("[2]", ref["poi_name"])
        )
        ans = targets[0]
        dist_km = round(float(ans.get("dist_m", 0)) / 1000, 2)
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": [
                    {
                        "id": ans.get("id"),
                        "geo_wkt": ans.get("geo_wkt"),
                        "dist_km": dist_km,
                        "poi_name": ans.get("poi_name"),
                    }
                ],
                "answer_type": "distance",
                "id": f"knn+distance-{len(results) + 1:03d}",
                "type": "knn+distance",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def generate_knn_direction_name(n=100) -> list[dict]:
    tmpls = load_templates("knn:direction+name")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="knn:direction+name")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        dir_label, dir_pred_tmpl = random.choice(DIRECTIONS)
        lat, lon = ref["lat"], ref["lon"]
        dir_pred = dir_pred_tmpl.format(lat=lat, lon=lon)
        sql = f"""SELECT p.osm_id AS id,
            ST_AsText(ST_Transform(p.way,4326)) AS geo_wkt, p.name AS poi_name
            FROM planet_osm_point p
            WHERE p.{main_cat} ILIKE '{sub_cat}' AND p.name IS NOT NULL
              AND p.osm_id <> {ref["id"]}
              AND {dir_pred}
            ORDER BY p.way <-> ST_Transform(ST_GeomFromText('{ref["geo_wkt"]}',4326),3857)
            LIMIT 1;"""
        try:
            targets = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        if not targets:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls)
            .replace("[1]", label)
            .replace("[2]", ref["poi_name"])
            .replace("[3]", dir_label)
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": [targets[0]],
                "answer_type": "name",
                "id": f"knn:direction+name-{len(results) + 1:03d}",
                "type": "knn:direction+name",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                    "[3]": {"direction": dir_label},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def generate_range_name(n=100) -> list[dict]:
    tmpls = load_templates("range+name")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="range+name")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        dist_km = random.choice([1, 2, 3, 5, 10, 20, 50])
        sql = f"""SELECT id, geo_wkt, poi_name FROM pois
            WHERE ST_DWithin(geometry,ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography,{dist_km * 1000})
              AND {main_cat} ILIKE '{sub_cat}' AND poi_name IS NOT NULL
              AND id <> {ref["id"]}
            ORDER BY geometry <-> ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography;"""
        try:
            targets = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        if not targets:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls)
            .replace("[1]", label)
            .replace("[2]", f"{dist_km} km")
            .replace("[3]", ref["poi_name"])
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": targets,
                "answer_type": "name",
                "id": f"range+name-{len(results) + 1:03d}",
                "type": "range+name",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"distance": dist_km * 1000, "text": f"{dist_km} km"},
                    "[3]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def generate_range_loc(n=100) -> list[dict]:
    tmpls = load_templates("range+loc")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="range+loc")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        dist_km = random.choice([1, 2, 3, 5, 10, 20])
        sql = f"""SELECT id, geo_wkt, poi_name FROM pois
            WHERE ST_DWithin(geometry,ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography,{dist_km * 1000})
              AND {main_cat} ILIKE '{sub_cat}' AND poi_name IS NOT NULL
              AND id <> {ref["id"]}
            ORDER BY geometry <-> ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography;"""
        try:
            targets = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        if not targets:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls)
            .replace("[1]", label)
            .replace("[2]", f"{dist_km} km")
            .replace("[3]", ref["poi_name"])
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": targets,
                "answer_type": "loc",
                "id": f"range+loc-{len(results) + 1:03d}",
                "type": "range+loc",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"distance": dist_km * 1000, "text": f"{dist_km} km"},
                    "[3]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def generate_range_count(n=100) -> list[dict]:
    tmpls = load_templates("range+count")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="range+count")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        dist_km = random.choice([1, 2, 3, 5, 10, 20])
        sql = f"""SELECT COUNT(*) AS count FROM pois
            WHERE ST_DWithin(geometry,ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography,{dist_km * 1000})
              AND {main_cat} ILIKE '{sub_cat}'
              AND id <> {ref["id"]};"""
        try:
            rows = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        count = rows[0].get("count", 0) if rows else 0
        if count == 0:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls)
            .replace("[1]", label)
            .replace("[2]", f"{dist_km} km")
            .replace("[3]", ref["poi_name"])
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": [{"count": count}],
                "answer_type": "count",
                "id": f"range+count-{len(results) + 1:03d}",
                "type": "range+count",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"distance": dist_km * 1000, "text": f"{dist_km} km"},
                    "[3]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def generate_range_direction_name(n=100) -> list[dict]:
    tmpls = load_templates("range:direction+name")
    results, fails, seen = [], 0, set()
    pbar = tqdm(total=n, desc="range:direction+name")
    while len(results) < n:
        if fails > 300:
            break
        ref = get_ref()
        if not ref:
            fails += 1
            continue
        main_cat, sub_cat = pick_target_cat()
        dist_km = random.choice([2, 5, 10, 20, 50])
        dir_label, dir_pred_tmpl = random.choice(DIRECTIONS)
        lat, lon = ref["lat"], ref["lon"]
        dir_pred = dir_pred_tmpl.format(lat=lat, lon=lon)
        sql = f"""SELECT p.osm_id AS id,
            ST_AsText(ST_Transform(p.way,4326)) AS geo_wkt, p.name AS poi_name
            FROM planet_osm_point p
            WHERE p.{main_cat} ILIKE '{sub_cat}' AND p.name IS NOT NULL
              AND p.osm_id <> {ref["id"]}
              AND ST_DWithin(ST_Transform(p.way,4326)::geography,
                  ST_GeomFromText('{ref["geo_wkt"]}',4326)::geography, {dist_km * 1000})
              AND {dir_pred}
            ORDER BY p.way <-> ST_Transform(ST_GeomFromText('{ref["geo_wkt"]}',4326),3857);"""
        try:
            targets = run_sql(sql)
        except (psycopg2.Error, IndexError, KeyError):
            fails += 1
            continue
        if not targets:
            fails += 1
            continue
        fails = 0
        label = vn_label(sub_cat)
        q = nfc(
            random.choice(tmpls)
            .replace("[1]", label)
            .replace("[2]", f"{dist_km} km")
            .replace("[3]", ref["poi_name"])
            .replace("[4]", dir_label)
        )
        if q in seen:
            fails += 1
            continue
        seen.add(q)
        results.append(
            {
                "question": q,
                "question_surfaces": surfaces(q),
                "sql": sql.strip(),
                "answers": targets,
                "answer_type": "name",
                "id": f"range:direction+name-{len(results) + 1:03d}",
                "type": "range:direction+name",
                "question_entities": {
                    "[1]": {"main_category": main_cat, "sub_category": sub_cat},
                    "[2]": {"distance": dist_km * 1000, "text": f"{dist_km} km"},
                    "[3]": {"poi_name": ref["poi_name"], "geo_wkt": ref["geo_wkt"]},
                    "[4]": {"direction": dir_label},
                },
            }
        )
        pbar.update(1)
    pbar.close()
    return results


def main() -> None:
    """Generate VN-GeoQA questions for all eight types from the `osm_vn` database."""
    parser = argparse.ArgumentParser(
        description="Generate VN-GeoQA benchmark questions from PostGIS."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="seeds Python choices and per-call TABLESAMPLE REPEATABLE seeds",
    )
    parser.add_argument("--count", type=int, default=100, help="questions per type")
    parser.add_argument("--output", default="questions_vi", help="output directory")
    args = parser.parse_args()

    random.seed(args.seed)
    os.makedirs(args.output, exist_ok=True)
    # Only clear question files so provenance sidecars (e.g. MANIFEST.json) survive.
    for f in os.listdir(args.output):
        if f.endswith(".jsonl"):
            os.remove(os.path.join(args.output, f))

    generators = [
        (generate_knn_name, "knn+name.jsonl"),
        (generate_knn_loc, "knn+loc.jsonl"),
        (generate_knn_distance, "knn+distance.jsonl"),
        (generate_knn_direction_name, "knn:direction+name.jsonl"),
        (generate_range_name, "range+name.jsonl"),
        (generate_range_loc, "range+loc.jsonl"),
        (generate_range_count, "range+count.jsonl"),
        (generate_range_direction_name, "range:direction+name.jsonl"),
    ]
    total = 0
    for gen_fn, fname in generators:
        qs = gen_fn(args.count)
        save(qs, fname, args.output)
        total += len(qs)
    print(f"\nTotal: {total} questions across {len(generators)} template types")


if __name__ == "__main__":
    main()
