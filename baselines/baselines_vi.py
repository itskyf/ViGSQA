"""
baselines_vi.py — runs GS-QA baselines on Vietnamese VN-GeoQA data.

Patches baselines.py at runtime:
  - QUESTIONS_DIR  → generator/questions_vi/
  - DB_PARAMS      → osm_vn (via PG* env)
  - CACHE_DIR      → cache_vi/
  - PROMPT_FILES   → Vietnamese prompts for direct and text2sql baselines
  - evaluate.get_osm_value → handles geo_wkt / dist_km field names
  - build_model    → llamacpp:<tag> routes to ChatOpenAI against llama.cpp /v1

Usage (same flags as baselines.py):
  python baselines_vi.py --model llamacpp:ornith --baseline direct --mode smoke
  python baselines_vi.py --model llamacpp:ornith --baseline text2sql --mode full
"""

import importlib as _importlib
import json as _json
import os as _os
import re as _re
import sys
from pathlib import Path

import evaluate as _ev
from langchain_openai import ChatOpenAI
from shapely import from_wkt as _from_wkt

import baselines as _b

try:
    import psycopg2 as _pg
except ImportError:
    # Optional: only used by the _loc_from_db fallback lookup.
    _pg = None

ROOT = Path(__file__).parent

# Vietnam bounding box and frozen evaluation tolerances.
VN_LAT_MIN = 8
VN_LAT_MAX = 24
VN_LON_MIN = 100
VN_LON_MAX = 110
MIN_COORDS_FOR_PAIR = 2
DISTANCE_ERROR_NORM_M = 5e5
MATCH_REL_TOLERANCE = 0.1

# ── Import and patch baselines ────────────────────────────────────────────────
# 1. Vietnamese questions directory
_b.QUESTIONS_DIR = ROOT.parent / "generator" / "questions_vi"

# 2. Vietnamese PostGIS database (same PG* env convention as scripts/*.sh)
_b.DB_PARAMS = dict(
    host=_os.getenv("PGHOST", "127.0.0.1"),
    dbname=_os.getenv("PGDATABASE", "osm_vn"),
    user=_os.getenv("PGUSER", "postgres"),
    password=_os.getenv("PGPASSWORD", "postgres"),
    port=int(_os.getenv("PGPORT", "5432")),
)

# 3. Separate cache so Vietnamese runs don't collide with English cache
_b.CACHE_DIR = ROOT / "cache_vi"
_b.CACHE_DIR.mkdir(exist_ok=True)

# 4. Vietnamese prompts (direct + text2sql)
_b.PROMPT_FILES["direct_answer"] = ROOT / "baseline_prompts" / "direct_answer_vi.txt"
_b.PROMPT_FILES["direct_json_parse"] = (
    ROOT / "baseline_prompts" / "direct_json_parse_vi.txt"
)
_b.PROMPT_FILES["sql_generate"] = ROOT / "baseline_prompts" / "text2sql_generate_vi.txt"
_b.PROMPT_FILES["sql_answer"] = ROOT / "baseline_prompts" / "text2sql_answer_vi.txt"
_b.PROMPT_FILES["sql_json_parse"] = (
    ROOT / "baseline_prompts" / "text2sql_json_parse_vi.txt"
)

# ── Patch evaluate.get_osm_value for VN-GeoQA field names ────────────────────
# VN-GeoQA answers use:
#   geo_wkt  (WKT string) instead of geometry
#   dist_km  (float, kilometres) instead of distance (metres)
_orig_get_osm_value = _ev.get_osm_value


def _vn_get_osm_value(json_obj, value_label):
    if value_label == "location":
        wkt = json_obj.get("geometry") or json_obj.get("geo_wkt")
        if not wkt:
            return None
        point = _from_wkt(wkt).centroid
        return {"lon": point.x, "lat": point.y}

    if value_label == "distance":
        if "distance" in json_obj:
            return json_obj["distance"]
        if "dist_km" in json_obj:
            return json_obj["dist_km"] * 1000  # km → metres
        return None

    if value_label == "address":
        # VN-GeoQA answers have no address fields; returning None causes the
        # evaluator to skip the geocoding path (which requires address_cache writes).
        return None

    if value_label == "name":
        # VN-GeoQA answers use poi_name; fall back to original which also
        # checks poi_name.
        return json_obj.get("poi_name") or _orig_get_osm_value(json_obj, value_label)

    return _orig_get_osm_value(json_obj, value_label)


_ev.get_osm_value = _vn_get_osm_value

# baselines.py calls importlib.reload(evaluate_mod) inside main(), which resets
# our patch. Intercept reload to re-apply the patch every time evaluate is reloaded.
_orig_reload = _importlib.reload


def _reload_with_patch(module):
    result = _orig_reload(module)
    if getattr(module, "__name__", "") == "evaluate":
        module.get_osm_value = _vn_get_osm_value
    return result


_importlib.reload = _reload_with_patch

# ── Patch evaluate_answers for VN-GeoQA ──────────────────────────────────────
# Two fixes:
#   1. loc-type: evaluation skips when address=None; instead compare lon/lat
#      directly from parsed JSON {"lon": x, "lat": y} to true geo_wkt coordinates.
#   2. count/distance text eval: num2words() produces English words; Vietnamese
#      model outputs digits — compare as digits instead.

_orig_evaluate_answers = _b.evaluate_answers


def _loc_from_db(poi_name: str):
    """Look up POI centroid lon/lat by name in the VN PostGIS DB."""
    # psycopg2 is optional; without it there is simply no DB fallback.
    if _pg is None:
        return None
    try:
        conn = _pg.connect(**_b.DB_PARAMS)
        conn.set_session(readonly=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT ST_X(ST_Centroid(geometry::geometry)), "
            "ST_Y(ST_Centroid(geometry::geometry))"
            " FROM pois WHERE poi_name ILIKE %s LIMIT 1",
            (f"%{poi_name}%",),
        )
        row = cur.fetchone()
        conn.close()
        return {"lon": float(row[0]), "lat": float(row[1])} if row else None
    except (_pg.Error, TypeError, ValueError):
        return None


def _vn_evaluate_answers(
    questions, answers, parsed_answers, evaluate_mod, geocoder, geod, prefix=""
):
    text_eval, parsed_eval = _orig_evaluate_answers(
        questions, answers, parsed_answers, evaluate_mod, geocoder, geod, prefix=prefix
    )

    # Load sql_exec cache — provides raw lon/lat or poi_name from SQL results.
    # Only for text2sql runs; direct/rag should not use SQL execution results.
    exec_by_id: dict = {}

    _model_arg = ""
    _baseline_arg = ""
    for _j, _a in enumerate(sys.argv):
        if _a == "--model" and _j + 1 < len(sys.argv):
            _model_arg = sys.argv[_j + 1]
        if _a == "--baseline" and _j + 1 < len(sys.argv):
            _baseline_arg = sys.argv[_j + 1]
    if "text2sql" in _baseline_arg or _baseline_arg == "all":
        _exec_path = _b.CACHE_DIR / _model_arg / "sql_exec.json"
        if _exec_path.exists():
            try:
                for item in _json.load(open(_exec_path)):
                    exec_by_id[item["id"]] = item.get("records", [])
            except (KeyError, OSError, ValueError):
                pass

    for i, q in enumerate(questions):
        qtype = q["type"]

        # Fix 1: loc-type — compare predicted coordinates to true geo_wkt.
        # Priority: (a) parsed JSON lon/lat, (b) sql_exec lon/lat,
        # (c) DB lookup by poi_name.
        if "loc" in qtype:
            for ans in q["answers"]:
                true_loc = _vn_get_osm_value(ans, "location")
                if true_loc is None:
                    continue
                pred_loc = None

                # (a) parsed JSON lon/lat
                for p in parsed_answers[i]:
                    try:
                        pred_loc = {
                            "lon": float(p.get("lon", p.get("longitude", None))),
                            "lat": float(p.get("lat", p.get("latitude", None))),
                        }
                        break
                    except (TypeError, ValueError):
                        pass

                # (b) sql_exec result has lon/lat columns
                if pred_loc is None and q["id"] in exec_by_id:
                    for rec in exec_by_id[q["id"]]:
                        out = rec.get("output", [])
                        if out and "lon" in out[0] and "lat" in out[0]:
                            pred_loc = {
                                "lon": float(out[0]["lon"]),
                                "lat": float(out[0]["lat"]),
                            }
                            break

                # (c) sql_exec has poi_name only — DB lookup for coordinates
                if pred_loc is None and q["id"] in exec_by_id:
                    for rec in exec_by_id[q["id"]]:
                        out = rec.get("output", [])
                        if out and "poi_name" in out[0]:
                            pred_loc = _loc_from_db(out[0]["poi_name"])
                            break

                # (d) raw text answer — regex extract decimal coordinates
                # Matches patterns like "10.123, 106.456" or "106.456 10.123"
                if pred_loc is None:
                    text = answers[i].get("content", "")
                    coords = _re.findall(r"(-?\d{1,3}\.\d{3,})", text)
                    if len(coords) >= MIN_COORDS_FOR_PAIR:
                        nums = [float(c) for c in coords[:4]]
                        # Heuristic: lat in [8, 24], lon in [100, 110] for Vietnam
                        pairs = [(nums[j], nums[j + 1]) for j in range(len(nums) - 1)]
                        for a_val, b_val in pairs:
                            if (
                                VN_LAT_MIN <= a_val <= VN_LAT_MAX
                                and VN_LON_MIN <= b_val <= VN_LON_MAX
                            ):
                                pred_loc = {"lat": a_val, "lon": b_val}
                                break
                            if (
                                VN_LAT_MIN <= b_val <= VN_LAT_MAX
                                and VN_LON_MIN <= a_val <= VN_LON_MAX
                            ):
                                pred_loc = {"lat": b_val, "lon": a_val}
                                break

                if pred_loc is None:
                    continue
                dists = evaluate_mod.evaluate_location(geod, [pred_loc], [true_loc])
                dist_err = min(dists[0] / DISTANCE_ERROR_NORM_M, 1.0)
                cur = parsed_eval[i].get("distance_error", float("inf"))
                if dist_err < cur:
                    parsed_eval[i]["distance_error"] = dist_err
                    parsed_eval[i]["attempted"] = True

        # Fix 2: count/distance text eval — digit-matching
        # (model outputs digits, not English words)
        if "count" in qtype or "distance" in qtype:
            mkey = "count" if "count" in qtype else "distance"
            text_answer = answers[i].get("content", "")
            pred_nums = [int(n) for n in _re.findall(r"\b\d+\b", text_answer)]
            if not pred_nums:
                continue
            for ans in q["answers"]:
                true_val = _vn_get_osm_value(ans, mkey)
                if true_val is None:
                    continue
                true_int = round(float(true_val))
                for pn in pred_nums:
                    match = (
                        pn == 0
                        if true_int == 0
                        else abs(pn - true_int) / true_int < MATCH_REL_TOLERANCE
                    )
                    if match:
                        if 1.0 > text_eval[i].get("F1", 0.0):
                            text_eval[i] = {
                                "attempted": True,
                                "P": 1.0,
                                "R": 1.0,
                                "F1": 1.0,
                            }
                        break

    return text_eval, parsed_eval


_b.evaluate_answers = _vn_evaluate_answers

# ── Model routing: llama.cpp via its OpenAI-compatible /v1 endpoint ──────────
# Model name syntax:  llamacpp:<tag>   e.g.  --model llamacpp:ornith
# The server (compose service or Colab llama-server) applies the GGUF's own
# chat template, so no per-model prompt formatting lives here.
# Reads LLAMACPP_URL env var (default http://localhost:8080).

_orig_build_model = _b.build_model


def _build_model_vi(model_name: str):
    if model_name.startswith("llamacpp:"):
        tag = model_name[len("llamacpp:") :]
        base_url = _os.environ.get("LLAMACPP_URL", "http://localhost:8080")
        return ChatOpenAI(
            model=tag,
            base_url=f"{base_url}/v1",
            api_key="not-needed",
            temperature=0,
            max_tokens=4096,
        )
    return _orig_build_model(model_name)


_b.build_model = _build_model_vi
_b.build_parser_model = _build_model_vi

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _b.main()
