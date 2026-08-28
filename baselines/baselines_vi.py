"""
baselines_vi.py — runs GS-QA baselines on Vietnamese VN-GeoQA data.

Patches the upstream pipeline module at runtime:
  - QUESTIONS_DIR  → generator/questions_vi/
  - DB_PARAMS      → osm_vn (via PG* env)
  - CACHE_DIR      → cache_vi/ds-{dataset_version}/pv-{prompt_version}/
  - PROMPT_FILES   → Vietnamese prompts for direct and text2sql baselines
  - evaluate.get_osm_value → handles geo_wkt / dist_km field names
  - build_model    → llamacpp:<tag> routes to ChatOpenAI against llama.cpp /v1

Cache and eval outputs are namespaced by dataset version (from the frozen
MANIFEST.json) and prompt version (sha256-8 of the active Vietnamese prompts),
so results from one freeze can never be reused for another.

Usage (run from the repo root; same flags as pipeline.py):
  python -m baselines.baselines_vi \
    --model llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M \
    --baseline direct --mode smoke
  python -m baselines.baselines_vi \
    --model llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M \
    --baseline text2sql --mode full
"""

import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from langchain_openai import ChatOpenAI
from shapely import from_wkt

from baselines import evaluate, pipeline
from vigsqa.settings import PostgresSettings

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
pipeline.QUESTIONS_DIR = ROOT.parent / "generator" / "questions_vi"

# 2. Vietnamese PostGIS database (same PG* env convention as scripts/*.sh)
pipeline.DB_PARAMS = PostgresSettings().connection_kwargs()

# 4. Vietnamese prompts (direct + text2sql) — bound before the prompt-version
# hash below so the namespace always reflects the prompts actually in use.
pipeline.PROMPT_FILES["direct_answer"] = (
    ROOT / "baseline_prompts" / "direct_answer_vi.txt"
)
pipeline.PROMPT_FILES["direct_json_parse"] = (
    ROOT / "baseline_prompts" / "direct_json_parse_vi.txt"
)
pipeline.PROMPT_FILES["sql_generate"] = (
    ROOT / "baseline_prompts" / "text2sql_generate_vi.txt"
)
pipeline.PROMPT_FILES["sql_answer"] = (
    ROOT / "baseline_prompts" / "text2sql_answer_vi.txt"
)
pipeline.PROMPT_FILES["sql_json_parse"] = (
    ROOT / "baseline_prompts" / "text2sql_json_parse_vi.txt"
)


def _dataset_version() -> str:
    """Dataset version from the frozen MANIFEST.json behind the symlink."""
    manifest = pipeline.QUESTIONS_DIR / "MANIFEST.json"
    try:
        return json.loads(manifest.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def _prompt_version() -> str:
    """sha256-8 over the active Vietnamese prompt files."""
    h = hashlib.sha256()
    for key in (
        "direct_answer",
        "direct_json_parse",
        "sql_generate",
        "sql_answer",
        "sql_json_parse",
    ):
        h.update(pipeline.PROMPT_FILES[key].read_bytes())
    return h.hexdigest()[:8]


DATASET_VERSION = _dataset_version()
PROMPT_VERSION = _prompt_version()

# 3. Separate, version-namespaced cache so results from one dataset/prompt
# freeze can never be reused for another (and never collide with English runs).
pipeline.CACHE_DIR = (
    ROOT / "cache_vi" / f"ds-{DATASET_VERSION}" / f"pv-{PROMPT_VERSION}"
)
pipeline.CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Provisional eval CSVs go to a namespaced results dir (official reporting is
# T03's job; these must never be described as benchmark scores).
RESULTS_DIR = ROOT.parent / "results" / f"ds-{DATASET_VERSION}"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_orig_save_eval = pipeline.save_eval


def _save_eval_vi(text_eval, parsed_eval, questions, model_name, prefix):
    # save_eval resolves pipeline.ROOT at call time; swap it for the call.
    original_root = pipeline.ROOT
    pipeline.ROOT = RESULTS_DIR
    try:
        return _orig_save_eval(text_eval, parsed_eval, questions, model_name, prefix)
    finally:
        pipeline.ROOT = original_root


pipeline.save_eval = _save_eval_vi

# ── Patch evaluate.get_osm_value for VN-GeoQA field names ────────────────────
# VN-GeoQA answers use:
#   geo_wkt  (WKT string) instead of geometry
#   dist_km  (float, kilometres) instead of distance (metres)
_orig_get_osm_value = evaluate.get_osm_value


# Upstream 45-degree compass sectors as (exclusive upper bound, VN label).
VN_SECTORS = [
    (22.5, "bắc"),
    (67.5, "đông bắc"),
    (112.5, "đông"),
    (157.5, "đông nam"),
    (202.5, "nam"),
    (247.5, "tây nam"),
    (292.5, "tây"),
    (337.5, "tây bắc"),
    (360.0, "bắc"),
]


def _vn_get_angle_desc(angle) -> str:
    """Vietnamese compass sector of an azimuth, upstream's 45-degree sectors."""
    a = float(angle) % 360
    return next(label for bound, label in VN_SECTORS if a < bound)


def _vn_get_osm_value(json_obj, value_label):
    if value_label == "location":
        wkt = json_obj.get("geometry") or json_obj.get("geo_wkt")
        if not wkt:
            return None
        point = from_wkt(wkt).centroid
        return {"lon": point.x, "lat": point.y}

    if value_label == "distance":
        if "distance" in json_obj:
            return json_obj["distance"]
        if "dist_km" in json_obj:
            return json_obj["dist_km"] * 1000  # km → metres
        return None

    if value_label == "angle_description":
        # v2 answers carry only the numeric angle; derive the Vietnamese sector.
        angle = json_obj.get("angle")
        return None if angle is None else _vn_get_angle_desc(angle)

    if value_label == "address":
        # VN-GeoQA answers have no address fields; returning None causes the
        # evaluator to skip the geocoding path (which requires address_cache writes).
        return None

    if value_label == "name":
        # VN-GeoQA answers use poi_name; fall back to original which also
        # checks poi_name.
        return json_obj.get("poi_name") or _orig_get_osm_value(json_obj, value_label)

    return _orig_get_osm_value(json_obj, value_label)


evaluate.get_osm_value = _vn_get_osm_value
evaluate.get_angle_desc = _vn_get_angle_desc

# pipeline.py reloads evaluate inside main(), which resets our patch. Intercept
# reload to re-apply the patch every time evaluate is reloaded.
_orig_reload = importlib.reload


def _reload_with_patch(module):
    result = _orig_reload(module)
    if getattr(module, "__name__", "").endswith("evaluate"):
        module.get_osm_value = _vn_get_osm_value
        module.get_angle_desc = _vn_get_angle_desc
    return result


importlib.reload = _reload_with_patch

# ── Patch evaluate_answers for VN-GeoQA ──────────────────────────────────────
# Two fixes:
#   1. loc-type: evaluation skips when address=None; instead compare lon/lat
#      directly from parsed JSON {"lon": x, "lat": y} to true geo_wkt coordinates.
#   2. count/distance text eval: num2words() produces English words; Vietnamese
#      model outputs digits — compare as digits instead.

_orig_evaluate_answers = pipeline.evaluate_answers


def _loc_from_db(poi_name: str):
    """Look up POI centroid lon/lat by name in the VN PostGIS DB."""
    try:
        conn = psycopg.connect(**pipeline.DB_PARAMS)
        conn.read_only = True
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
    except (psycopg.Error, TypeError, ValueError):
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
        _exec_path = pipeline.cache_path(_model_arg, "sql_exec")
        if _exec_path.exists():
            try:
                for item in json.load(open(_exec_path)):
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
                    coords = re.findall(r"(-?\d{1,3}\.\d{3,})", text)
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

        # Fix 2: count/distance/area/length text eval — digit-matching
        # (model outputs digits, not English words)
        if any(k in qtype for k in ("count", "distance", "area", "length")):
            mkey = next(
                k for k in ("area", "length", "count", "distance") if k in qtype
            )
            text_answer = answers[i].get("content", "")
            pred_nums = [
                float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", text_answer)
            ]
            if not pred_nums:
                continue
            for ans in q["answers"]:
                true_val = _vn_get_osm_value(ans, mkey)
                if true_val is None:
                    continue
                true_num = round(float(true_val))
                for pn in pred_nums:
                    match = (
                        pn == 0
                        if true_num == 0
                        else abs(pn - true_num) / true_num < MATCH_REL_TOLERANCE
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


pipeline.evaluate_answers = _vn_evaluate_answers

# ── Model routing: llama.cpp via its OpenAI-compatible /v1 endpoint ──────────
# Model name syntax:  llamacpp:<tag>
# Example: --model llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M
# The server (compose service or Colab llama-server) applies the GGUF's own
# chat template, so no per-model prompt formatting lives here.
# Reads LLAMACPP_URL env var (default http://localhost:8000).

_orig_build_model = pipeline.build_model


def _build_model_vi(model_name: str):
    if model_name.startswith("llamacpp:"):
        tag = model_name[len("llamacpp:") :]
        base_url = os.environ.get("LLAMACPP_URL", "http://localhost:8000")
        return ChatOpenAI(
            model=tag,
            base_url=f"{base_url}/v1",
            api_key="not-needed",
            temperature=0,
            max_tokens=4096,
        )
    return _orig_build_model(model_name)


pipeline.build_model = _build_model_vi
pipeline.build_parser_model = _build_model_vi

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pipeline.main()
