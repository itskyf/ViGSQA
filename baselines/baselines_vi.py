"""
baselines_vi.py — runs GS-QA baselines on Vietnamese VN-GeoQA data.

Configures the upstream pipeline module for Vietnamese inference:
  - QUESTIONS_DIR  → generator/questions_vi/
  - DB_PARAMS      → osm_vn (via PG* env)
  - CACHE_DIR      → cache_vi/pv-{prompt_version}/
  - PROMPT_FILES   → Vietnamese prompts for direct and text2sql baselines
  - build_model    → every model is served by the external OpenAI-compatible
                     vLLM endpoint (standard OPENAI_* env vars, frozen profile)

Step caches are namespaced by the prompt version (sha256-8 of the active
Vietnamese prompts), so a prompt change never reuses another freeze's results.

Usage (run from the repo root; same flags as pipeline.py):
  python -m baselines.baselines_vi \
    --model ornith-ai/Ornith-1.5-9B-NVFP4 \
    --baseline direct --mode smoke
  python -m baselines.baselines_vi \
    --model ornith-ai/Ornith-1.5-9B-NVFP4 \
    --baseline text2sql --mode full
"""

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote_plus

from langchain_community.cache import SQLAlchemyMd5Cache
from langchain_core.globals import set_llm_cache
from langchain_core.load import loads
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from baselines import pipeline
from vigsqa.settings import PostgresSettings

ROOT = Path(__file__).parent

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

# 3. Separate, prompt-namespaced cache so results from one prompt freeze can
# never be reused for another (and never collide with English runs).
pipeline.CACHE_DIR = ROOT / "cache_vi" / f"pv-{PROMPT_VERSION}"
pipeline.CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Model routing: external OpenAI-compatible vLLM endpoint ──────────────────
# The model name is the id the server serves, e.g.
#   --model ornith-ai/Ornith-1.5-9B-NVFP4
# The endpoint is assumed already running and is addressed only through the
# standard OpenAI env vars (OPENAI_API_BASE / OPENAI_BASE_URL, OPENAI_API_KEY);
# the key fallback keeps keyless local vLLM usable without secrets. vLLM-only
# samplers ride in extra_body; thinking stays on via the server-side chat
# template's default behavior (no chat_template_kwargs). No tool calls.

# Frozen inference profile, identical for both official models. It is part of
# the LangChain cache key through `_get_llm_string()`, so a profile change
# re-keys the cache without any extra machinery.
INFERENCE_PROFILE = dict(
    temperature=1.0,
    top_p=0.95,
    presence_penalty=1.5,
    seed=42,
    max_completion_tokens=32768,
    extra_body={"top_k": 20, "min_p": 0.0, "repetition_penalty": 1.0},
)


def build_model_vi(model_name: str):
    return ChatOpenAI(
        model=model_name,
        api_key=os.environ.get("OPENAI_API_KEY") or "not-needed",
        **INFERENCE_PROFILE,
    )


pipeline.build_model = build_model_vi
pipeline.build_parser_model = build_model_vi

# ── PostgreSQL LLM cache (LangChain) ─────────────────────────────────────────
# The cache is the skip layer for LLM steps; the JSON step files remain
# write-through artifacts. Colab/in-process runs must call setup_llm_cache().
LLM_CACHE_DBNAME = os.environ.get("LLM_CACHE_DBNAME", "llm_cache")

# Cache identity follows the model request, not the endpoint serving it, so
# exactly these transport-only fields are stripped before lookup/update.
_TRANSPORT_ONLY_KEYS = ("openai_api_base", "openai_api_key")

# Allowlist for deserializing cached rows: what langchain falls back to when
# none is passed, stated explicitly so a lookup does not emit a deprecation
# warning. Changing this changes what a stored row may revive.
CACHE_ALLOWED_OBJECTS = "core"


def _normalize_llm_string(llm_string: str) -> str:
    """Drop transport-only fields from a LangChain cache key.

    The same model/generation parameters at a different endpoint must share
    cache rows. On a parse failure the string passes through unchanged, so the
    failure mode is endpoint-coupled keys (redundant inference), never a false
    hit. ponytail: if langchain-openai adds another transport-only kwarg to
    _get_llm_string, add it to _TRANSPORT_ONLY_KEYS or keys fragment per
    endpoint configuration.
    """
    head, sep, tail = llm_string.rpartition("---")
    if not head:
        return llm_string
    try:
        payload = json.loads(head)
    except json.JSONDecodeError:
        return llm_string
    kwargs = payload.get("kwargs") if isinstance(payload, dict) else None
    if not isinstance(kwargs, dict):
        return llm_string
    for key in _TRANSPORT_ONLY_KEYS:
        kwargs.pop(key, None)
    return json.dumps(payload, sort_keys=True) + sep + tail


class TransportNormalizedMd5Cache(SQLAlchemyMd5Cache):
    """`SQLAlchemyMd5Cache` that keys on the model request, ignoring endpoint.

    Model name, temperature, and the other generation kwargs
    (`max_completion_tokens`, `extra_body`) stay keyed."""

    def lookup(self, prompt, llm_string):
        """Cached generations for the normalized request key, or `None` on a miss.

        Overrides the upstream body only to deserialize with an explicit
        `allowed_objects`: the upstream `SQLAlchemyMd5Cache.lookup` passes none,
        which makes langchain warn on every hit and then fall back to `"core"` —
        the same allowlist, stated explicitly.

        Version-pinned internal dependency, as in `evict()`: delegates to the
        locked `SQLAlchemyMd5Cache._search_rows` (langchain-community 0.4.2;
        selects `response` by `prompt_md5` + `llm` + `prompt`, ordered by `idx`).
        """
        rows = self._search_rows(prompt, _normalize_llm_string(llm_string))
        if rows:
            return [
                loads(row[0], allowed_objects=CACHE_ALLOWED_OBJECTS) for row in rows
            ]
        return None

    def update(self, prompt, llm_string, return_val):
        super().update(prompt, _normalize_llm_string(llm_string), return_val)

    def evict(self, prompt: str, llm_string: str) -> None:
        """Delete the rows for exactly one request key, normalized like
        lookup/update — the runtime retry loop calls this so an invalid
        completion can never survive as the canonical cache entry.

        Version-pinned internal dependency: delegates to the locked
        `SQLAlchemyMd5Cache._delete_previous` (langchain-community 0.4.2;
        deletes by `prompt_md5` + `llm` + `prompt`). A locked-version upgrade
        must re-verify this method and the T09 probes.
        """
        with Session(self.engine) as session, session.begin():
            self._delete_previous(session, prompt, _normalize_llm_string(llm_string))


def llm_cache_engine():
    """SQLAlchemy engine for the `llm_cache` database (PG* env credentials)."""
    s = PostgresSettings()
    password = quote_plus(s.password.get_secret_value())
    url = (
        f"postgresql+psycopg://{quote_plus(s.user)}:{password}"
        f"@{s.host}:{s.port}/{LLM_CACHE_DBNAME}"
    )
    # pool_pre_ping: overnight runs must survive a restarted postgres service.
    return create_engine(url, pool_pre_ping=True)


def setup_llm_cache() -> None:
    """Point LangChain's global LLM cache at the `llm_cache` Postgres database.

    A database that cannot be reached fails loudly here — never falls back
    silently to uncached inference.
    """
    s = PostgresSettings()
    set_llm_cache(TransportNormalizedMd5Cache(llm_cache_engine()))
    print(f"[llm-cache] normalized md5 cache -> {s.host}:{s.port}/{LLM_CACHE_DBNAME}")


# ── Text2SQL stage output validation ─────────────────────────────────────────
# ViGSQA policy on top of pipeline's opt-in mechanism: a successful transport
# call is not automatically a successful step. Corresponding Direct and
# Text2SQL stages share the answer/JSON contracts; upstream/non-Vietnamese runs
# never import this layer.

STAGE_MAX_ATTEMPTS = 3


def sql_block_error(content, finish_reason):
    """`sql_generate` contract: at least one fenced SQL block accepted by the
    same parser the execution step uses (`extract_sql_blocks`).

    `finish_reason` is diagnostic only — a complete block stays accepted even
    when the generation then hit the token limit.
    """
    if isinstance(content, str) and pipeline.extract_sql_blocks(content):
        return None
    return "invalid_sql_output: no parseable SQL block"


def answer_text_error(content, finish_reason):
    """`sql_answer` contract: non-empty free-form text that terminated
    normally.

    A `length` finish means the answer never terminated, which also rejects
    runaway/repetitive answers by termination status — no repetition
    heuristics.
    """
    if not isinstance(content, str) or not content.strip():
        return "invalid_answer_output: empty completion"
    if finish_reason == "length":
        return "invalid_answer_output: token limit exhausted"
    return None


def json_block_error(content, finish_reason):
    """`sql_json_parse` contract: at least one fenced JSON block accepted by
    the same parser the evaluation step uses (`extract_json_blocks`).

    A complete parseable block stays accepted even if trailing generation hit
    the token limit.
    """
    if isinstance(content, str) and pipeline.extract_json_blocks(content):
        return None
    return "invalid_json_output: no parseable JSON block"


def _stage_validation(cache_key):
    """The stage's structural validation policy, if it is an LLM stage."""
    checks = {
        "direct_answer": answer_text_error,
        "direct_json_parse": json_block_error,
        "sql_generate": sql_block_error,
        "sql_answer": answer_text_error,
        "sql_json_parse": json_block_error,
    }
    check = checks.get(cache_key)
    return pipeline.StageValidation(check, STAGE_MAX_ATTEMPTS) if check else None


_orig_step_generate_answers = pipeline.step_generate_answers


def _step_generate_answers_vi(
    questions,
    model,
    model_name,
    cache_key,
    system_prompt,
    llm_concurrency=1,
    stage=None,
):
    return _orig_step_generate_answers(
        questions,
        model,
        model_name,
        cache_key,
        system_prompt,
        llm_concurrency,
        stage if stage is not None else _stage_validation(cache_key),
    )


_orig_step_answer_from_records = pipeline.step_answer_from_records


def _step_answer_from_records_vi(
    questions,
    sql_answers,
    sql_outputs,
    model,
    model_name,
    llm_concurrency=1,
    stage=None,
):
    return _orig_step_answer_from_records(
        questions,
        sql_answers,
        sql_outputs,
        model,
        model_name,
        llm_concurrency,
        stage if stage is not None else _stage_validation("sql_answer"),
    )


_orig_step_parse_to_json = pipeline.step_parse_to_json


def _step_parse_to_json_vi(
    questions,
    answers,
    parser_model,
    model_name,
    cache_key,
    json_prompt_key,
    llm_concurrency=1,
    stage=None,
):
    return _orig_step_parse_to_json(
        questions,
        answers,
        parser_model,
        model_name,
        cache_key,
        json_prompt_key,
        llm_concurrency,
        stage if stage is not None else _stage_validation(cache_key),
    )


pipeline.step_generate_answers = _step_generate_answers_vi
pipeline.step_answer_from_records = _step_answer_from_records_vi
pipeline.step_parse_to_json = _step_parse_to_json_vi


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    setup_llm_cache()
    pipeline.main()
