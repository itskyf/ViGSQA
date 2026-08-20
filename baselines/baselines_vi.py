"""
baselines_vi.py — runs GS-QA baselines on Vietnamese VN-GeoQA data.

Patches baselines.py at runtime:
  - QUESTIONS_DIR  → generator/questions_vi/
  - DB_PARAMS      → osm_vn
  - CACHE_DIR      → cache_vi/
  - PROMPT_FILES   → text2sql_generate_vi.txt for text2sql baseline
  - evaluate.get_osm_value → handles geo_wkt / dist_km field names

Usage (same flags as baselines.py):
  python baselines_vi.py --model sonnet4.6 --baseline direct
  python baselines_vi.py --model sonnet4.6 --baseline text2sql
  python baselines_vi.py --model sonnet4.6 --baseline all
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Import and patch baselines ────────────────────────────────────────────────
import baselines as _b

# 1. Vietnamese questions directory
_b.QUESTIONS_DIR = ROOT.parent / "generator" / "questions_vi"

# 2. Vietnamese PostGIS database
_b.DB_PARAMS = dict(
    host="localhost",
    dbname="osm_vn",
    user="postgres",
    password="postgres",
    port=5432,
)

# 3. Separate cache so Vietnamese runs don't collide with English cache
_b.CACHE_DIR = ROOT / "cache_vi"
_b.CACHE_DIR.mkdir(exist_ok=True)

# 4. Vietnam-specific text2sql prompts
_b.PROMPT_FILES["sql_generate"]   = ROOT / "baseline_prompts" / "text2sql_generate_vi.txt"
_b.PROMPT_FILES["sql_answer"]     = ROOT / "baseline_prompts" / "text2sql_answer_vi.txt"
_b.PROMPT_FILES["sql_json_parse"] = ROOT / "baseline_prompts" / "text2sql_json_parse_vi.txt"

# ── Patch evaluate.get_osm_value for VN-GeoQA field names ────────────────────
# VN-GeoQA answers use:
#   geo_wkt  (WKT string) instead of geometry
#   dist_km  (float, kilometres) instead of distance (metres)
import evaluate as _ev
from shapely import from_wkt as _from_wkt

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
        # VN-GeoQA answers use poi_name; fall back to original which also checks poi_name.
        return json_obj.get("poi_name") or _orig_get_osm_value(json_obj, value_label)

    return _orig_get_osm_value(json_obj, value_label)


_ev.get_osm_value = _vn_get_osm_value

# baselines.py calls importlib.reload(evaluate_mod) inside main(), which resets
# our patch. Intercept reload to re-apply the patch every time evaluate is reloaded.
import importlib as _importlib

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
    try:
        import psycopg2 as _pg
        conn = _pg.connect(**_b.DB_PARAMS)
        cur = conn.cursor()
        cur.execute(
            "SELECT ST_X(ST_Centroid(geometry::geometry)), ST_Y(ST_Centroid(geometry::geometry))"
            " FROM pois WHERE poi_name ILIKE %s LIMIT 1",
            (f"%{poi_name}%",),
        )
        row = cur.fetchone()
        conn.close()
        return {"lon": float(row[0]), "lat": float(row[1])} if row else None
    except Exception:
        return None


def _vn_evaluate_answers(questions, answers, parsed_answers, evaluate_mod, geocoder, geod, prefix=""):
    text_eval, parsed_eval = _orig_evaluate_answers(
        questions, answers, parsed_answers, evaluate_mod, geocoder, geod, prefix=prefix
    )

    import re as _re
    import json as _json
    import glob as _glob

    # Load sql_exec cache — provides raw lon/lat or poi_name from SQL results.
    # Only for text2sql runs; direct/rag should not use SQL execution results.
    exec_by_id: dict = {}
    import sys as _sys
    _model_arg = ""
    _baseline_arg = ""
    for _j, _a in enumerate(_sys.argv):
        if _a == "--model" and _j + 1 < len(_sys.argv):
            _model_arg = _sys.argv[_j + 1]
        if _a == "--baseline" and _j + 1 < len(_sys.argv):
            _baseline_arg = _sys.argv[_j + 1]
    if "text2sql" in _baseline_arg or _baseline_arg == "all":
        _exec_path = _b.CACHE_DIR / _model_arg / "sql_exec.json"
        if _exec_path.exists():
            try:
                for item in _json.load(open(_exec_path)):
                    exec_by_id[item["id"]] = item.get("records", [])
            except Exception:
                pass

    for i, q in enumerate(questions):
        qtype = q["type"]

        # Fix 1: loc-type — compare predicted coordinates to true geo_wkt.
        # Priority: (a) parsed JSON lon/lat, (b) sql_exec lon/lat, (c) DB lookup by poi_name.
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
                            pred_loc = {"lon": float(out[0]["lon"]), "lat": float(out[0]["lat"])}
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
                    coords = _re.findall(r'(-?\d{1,3}\.\d{3,})', text)
                    if len(coords) >= 2:
                        nums = [float(c) for c in coords[:4]]
                        # Heuristic: lat in [8, 24], lon in [100, 110] for Vietnam
                        pairs = [(nums[j], nums[j+1]) for j in range(len(nums)-1)]
                        for a_val, b_val in pairs:
                            if 8 <= a_val <= 24 and 100 <= b_val <= 110:
                                pred_loc = {"lat": a_val, "lon": b_val}
                                break
                            if 8 <= b_val <= 24 and 100 <= a_val <= 110:
                                pred_loc = {"lat": b_val, "lon": a_val}
                                break

                if pred_loc is None:
                    continue
                dists = evaluate_mod.evaluate_location(geod, [pred_loc], [true_loc])
                dist_err = 1.0 if dists[0] > 5e5 else dists[0] / 5e5
                cur = parsed_eval[i].get("distance_error", float("inf"))
                if dist_err < cur:
                    parsed_eval[i]["distance_error"] = dist_err
                    parsed_eval[i]["attempted"] = True

        # Fix 2: count/distance text eval — digit-matching (model outputs digits, not English words)
        if "count" in qtype or "distance" in qtype:
            mkey = "count" if "count" in qtype else "distance"
            text_answer = answers[i].get("content", "")
            pred_nums = [int(n) for n in _re.findall(r'\b\d+\b', text_answer)]
            if not pred_nums:
                continue
            for ans in q["answers"]:
                true_val = _vn_get_osm_value(ans, mkey)
                if true_val is None:
                    continue
                true_int = int(round(float(true_val)))
                for pn in pred_nums:
                    match = pn == 0 if true_int == 0 else abs(pn - true_int) / true_int < 0.1
                    if match:
                        if 1.0 > text_eval[i].get("F1", 0.0):
                            text_eval[i] = {"attempted": True, "P": 1.0, "R": 1.0, "F1": 1.0}
                        break

    return text_eval, parsed_eval


_b.evaluate_answers = _vn_evaluate_answers

# ── llama.cpp server support (Qwen3 nothink mode) ────────────────────────────
# Model name syntax:  llamacpp:<tag>
#   e.g.  --model llamacpp:qwen3.5-9b   --parser-model llamacpp:qwen3.5-9b
#
# Uses the /completion endpoint with a pre-filled assistant prefix
# "<think>\n\n</think>\n\n" to skip Qwen3's chain-of-thought and get a direct
# answer. Falls back to the OpenAI-compatible /v1 endpoint for non-Qwen3
# models (e.g. Gemma) where thinking is not an issue.
#
# Reads LLAMACPP_URL env var (default http://localhost:8080).
# Set LLAMACPP_NOTHINK=0 to disable the nothink prefix (for non-thinking models).

import os as _os
import requests as _requests
from typing import Any, Iterator, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class _LlamaCppChat(BaseChatModel):
    """Thin LangChain wrapper around llama.cpp /completion.

    chat_format:
      "chatml"  — Qwen3/Mistral format (<|im_start|> ... <|im_end|>)
      "gemma"   — Gemma 4 format (<start_of_turn> ... <end_of_turn>)
    nothink:
      True — prepend <think>\\n\\n</think>\\n\\n to skip Qwen3 CoT
    """

    base_url: str
    chat_format: str = "chatml"
    nothink: bool = True
    max_tokens: int = 4096
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        return "llamacpp"

    def _build_prompt(self, messages: List[BaseMessage]) -> tuple[str, list[str]]:
        system_content = ""
        user_content = ""
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_content = msg.content
            elif isinstance(msg, HumanMessage):
                user_content = msg.content

        if self.chat_format == "gemma":
            prompt = ""
            if system_content:
                prompt += f"<start_of_turn>user\n{system_content}\n\n{user_content}<end_of_turn>\n"
            else:
                prompt += f"<start_of_turn>user\n{user_content}<end_of_turn>\n"
            prompt += "<start_of_turn>model\n"
            stop = ["<end_of_turn>", "<start_of_turn>"]
        else:  # chatml
            prompt = ""
            if system_content:
                prompt += f"<|im_start|>system\n{system_content}<|im_end|>\n"
            prompt += f"<|im_start|>user\n{user_content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"
            if self.nothink:
                prompt += "<think>\n\n</think>\n\n"
            stop = ["<|im_end|>", "<|im_start|>"]

        return prompt, stop

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> ChatResult:
        prompt, stop_seqs = self._build_prompt(messages)
        resp = _requests.post(
            f"{self.base_url}/completion",
            json={
                "prompt": prompt,
                "n_predict": self.max_tokens,
                "temperature": self.temperature,
                "stop": stop_seqs,
            },
            timeout=300,
        )
        try:
            resp.raise_for_status()
        except Exception as exc:
            import sys
            print(f"[llamacpp] HTTP {resp.status_code} — returning empty: {exc}", file=sys.stderr)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
        content = resp.json().get("content", "")
        # Gemma 4 inline thinking format: "<|channel>thought\n<channel|>answer"
        # Strip everything up to and including the last "<channel|>" marker.
        if "<channel|>" in content:
            content = content.split("<channel|>")[-1].strip()
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    @property
    def _identifying_params(self) -> dict:
        return {"base_url": self.base_url, "chat_format": self.chat_format, "nothink": self.nothink}


class _OllamaChat(BaseChatModel):
    """LangChain wrapper around Ollama /api/generate (raw chatml + nothink prefix)."""

    base_url: str
    model_tag: str
    nothink: bool = True
    max_tokens: int = 4096
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        return "ollama"

    def _build_prompt(self, messages: List[BaseMessage]) -> tuple[str, list[str]]:
        system_content = ""
        user_content = ""
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_content = msg.content
            elif isinstance(msg, HumanMessage):
                user_content = msg.content

        prompt = ""
        if system_content:
            prompt += f"<|im_start|>system\n{system_content}<|im_end|>\n"
        prompt += f"<|im_start|>user\n{user_content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        if self.nothink:
            prompt += "<think>\n\n</think>\n\n"
        stop = ["<|im_end|>", "<|im_start|>"]
        return prompt, stop

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> ChatResult:
        prompt, stop_seqs = self._build_prompt(messages)
        resp = _requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_tag,
                "prompt": prompt,
                "raw": True,
                "stream": False,
                "options": {
                    "num_predict": self.max_tokens,
                    "temperature": self.temperature,
                    "stop": stop_seqs,
                },
            },
            timeout=600,
        )
        try:
            resp.raise_for_status()
        except Exception as exc:
            import sys
            print(f"[ollama] HTTP {resp.status_code} — returning empty: {exc}", file=sys.stderr)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
        content = resp.json().get("response", "")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    @property
    def _identifying_params(self) -> dict:
        return {"base_url": self.base_url, "model_tag": self.model_tag, "nothink": self.nothink}


_orig_build_model = _b.build_model


def _build_model_vi(model_name: str):
    if model_name.startswith("llamacpp:"):
        tag = model_name[len("llamacpp:"):]
        base_url = _os.environ.get("LLAMACPP_URL", "http://localhost:8080")
        nothink = _os.environ.get("LLAMACPP_NOTHINK", "1") != "0"
        chat_format = "gemma" if "gemma" in tag.lower() else "chatml"
        return _LlamaCppChat(
            base_url=base_url,
            chat_format=chat_format,
            nothink=nothink,
            max_tokens=4096,
            temperature=0.0,
        )
    if model_name.startswith("ollama:"):
        tag = model_name[len("ollama:"):]
        base_url = _os.environ.get("OLLAMA_URL", "http://localhost:11434")
        nothink = _os.environ.get("OLLAMA_NOTHINK", "1") != "0"
        return _OllamaChat(
            base_url=base_url,
            model_tag=tag,
            nothink=nothink,
            max_tokens=4096,
            temperature=0.0,
        )
    return _orig_build_model(model_name)


_b.build_model = _build_model_vi
_b.build_parser_model = _build_model_vi

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _b.main()
