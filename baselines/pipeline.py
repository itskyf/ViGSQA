#!/usr/bin/env python3
"""
Unified baseline runner for SpatialQA.

Baselines
---------
  direct   - question → answer → json
  text2sql - question → SQL → records → answer → json
  rag      - question → vector retrieval → answer → json

Usage
-----
  python pipeline.py --model sonnet4.6 --baseline direct
  python pipeline.py --model gpt4o     --baseline text2sql
  python pipeline.py --model sonnet4.6 --baseline rag --embeddings nomic
  python pipeline.py --model sonnet4.6 --baseline all
  python pipeline.py --model sonnet4.6 --parser-model gpt4o --baseline all
  python pipeline.py --model sonnet4.6 --baseline direct \
      --clear-cache direct_answer,direct_json_parse
  python pipeline.py --model sonnet4.6 --baseline all    --clear-cache all
  python pipeline.py --model sonnet4.6 --baseline shuffled
  python pipeline.py --model qwen3.5:9b \
      --ollama-url https://my-ollama.example.com --baseline direct
  OLLAMA_HOST=https://my-ollama.example.com \
      python pipeline.py --model qwen3.5:9b --baseline direct
"""

import argparse
import ast
import datetime
import decimal
import importlib
import json
import logging
import operator as op
import os
import random
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from functools import cache
from glob import glob
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import psycopg
from geopy.geocoders import Nominatim
from langchain_core.caches import BaseCache
from langchain_core.documents import Document
from langchain_core.globals import get_llm_cache
from langchain_core.load import dumps
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from num2words import num2words
from psycopg.rows import dict_row
from pyproj import Geod
from tqdm import tqdm

logger = logging.getLogger(__name__)

# Optional model backends: only the selected model/provider needs them, so a
# missing package must not break importing this module.
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None

try:
    from langchain_chroma import Chroma
except ImportError:
    Chroma = None

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    HuggingFaceEmbeddings = None

try:
    from langchain_ollama import ChatOllama, OllamaEmbeddings
except ImportError:
    ChatOllama = OllamaEmbeddings = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
PROMPTS_DIR = ROOT / "baseline_prompts"
CACHE_DIR = ROOT / "cache"
QUESTIONS_DIR = ROOT / "selected_questions"

PROMPTS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# Frozen benchmark limits; values must not change (recorded artifacts depend on them).
MAX_QUESTIONS_PER_TYPE = 100
DISTANCE_ERROR_NORM_M = 5e5
EMBEDDING_BATCH_SIZE = 256
MAX_SHUFFLED_PARTS = 10
MAX_SHUFFLED_ANSWER_CHARS = 256

# ---------------------------------------------------------------------------
# Prompt files (written once on first run, then loaded from disk)
# ---------------------------------------------------------------------------

PROMPT_FILES = {
    "direct_answer": PROMPTS_DIR / "direct_answer.txt",
    "direct_json_parse": PROMPTS_DIR / "direct_json_parse.txt",
    "sql_generate": PROMPTS_DIR / "text2sql_generate.txt",
    "sql_answer": PROMPTS_DIR / "text2sql_answer.txt",
    "sql_json_parse": PROMPTS_DIR / "text2sql_json_parse.txt",
    "rag_answer": PROMPTS_DIR / "rag_answer.txt",
    "rag_json_parse": PROMPTS_DIR / "rag_json_parse.txt",
}


def load_prompt(key: str) -> str:
    path = PROMPT_FILES[key]
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text()


# ---------------------------------------------------------------------------
# Model setup
# ---------------------------------------------------------------------------


def build_model(model_name: str):
    if model_name == "sonnet4.6":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        return ChatAnthropic(
            model="claude-sonnet-4-6", temperature=0, max_tokens=4096, api_key=api_key
        )

    if model_name == "haiku4.5":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        return ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            temperature=0,
            max_tokens=4096,
            api_key=api_key,
        )

    if model_name == "gpt4o":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        return ChatOpenAI(
            model="gpt-4o", temperature=0, max_tokens=4096, api_key=api_key
        )

    # Any other name is treated as an Ollama model tag (e.g. qwen3.5:9b, llama3.1:8b).
    # Use OLLAMA_HOST env var or --ollama-url CLI flag to route to a remote instance.
    base_url = os.environ.get("OLLAMA_HOST", "https://ollama.com")
    return ChatOllama(
        model=model_name,
        temperature=0,
        num_ctx=4096,
        num_predict=4096,
        base_url=base_url,
    )


def build_parser_model(model_name: str):
    """Build the model used for the JSON-parsing step.
    Defaults to the same model as generation; pass a lighter model name to save cost."""
    return build_model(model_name)


# ---------------------------------------------------------------------------
# Rate-limited invocation
# ---------------------------------------------------------------------------


def _parse_wait_seconds(err_str: str, attempt: int) -> float:
    """Extract wait time from error message, or compute exponential backoff."""
    # Try 'try again in Xs' pattern
    m = re.search(r"try again in\s+([\d.]+)\s*s", err_str, re.IGNORECASE)
    if m:
        return float(m.group(1)) + 2
    # Sonnet: per-minute token limit → wait up to 60s + backoff
    base = 60
    return min(base * (2**attempt), 600)


def invoke_with_retry(model, messages, max_retries: int = 8):
    """Invoke model with exponential backoff on rate-limit (429) errors."""
    for attempt in range(max_retries):
        try:
            return model.invoke(messages)
        except Exception as e:
            err_str = str(e)
            is_rate_limit = (
                "429" in err_str
                or "rate_limit" in err_str.lower()
                or "rate limit" in err_str.lower()
                or "RateLimitError" in type(e).__name__
            )
            if is_rate_limit and attempt < max_retries - 1:
                wait = _parse_wait_seconds(err_str, attempt)
                print(
                    f"\n  [rate limit] attempt {attempt + 1}/{max_retries}"
                    f" — sleeping {wait:.0f}s …"
                )
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("Max retries exceeded")


# Terminal per-question model failures are cached explicitly ({"error": ...})
# so runs stay complete and resumable; a long unbroken streak means something
# systemic (server down, OOM) and still aborts with the cache preserved.
TERMINAL_FAILURE_STREAK = 10


def invoke_or_capture(model, messages) -> tuple[str, str | None, dict]:
    try:
        message = invoke_with_retry(model, messages)
        return message.content, None, _gen_metadata(message)
    except Exception as e:  # the error is frozen into the cache below
        logger.exception("LLM invoke failed; freezing the error into the cache")
        return "", str(e), {}


# Stage output validation (opt-in). A successful transport call is not
# automatically a successful step: callers that pass a `StageValidation` get
# each completion checked, and invalid ones retried on the identical request.
# The LLM cache write happens inside `.invoke()` *before* this check, so
# every invalid result must also evict its own cache row — otherwise the
# retry would replay the poisoned entry instead of generating.


class StageValidation(NamedTuple):
    """One stage's output-validation policy.

    `check(content, finish_reason)` returns `None` for a valid completion,
    else an error label; `max_attempts` bounds the identical-request retries.
    """

    check: Callable[[str, str | None], str | None]
    max_attempts: int = 1


def _finish_reason(message) -> str | None:
    """Termination status the backend reported ("stop", "length", …), or `None`.

    Preserved into stage validation as a termination fact only; the cause of a
    `length` finish (reasoning, truncation, repetition) is deliberately not
    assumed.
    """
    metadata = getattr(message, "response_metadata", None)
    return metadata.get("finish_reason") if isinstance(metadata, dict) else None


def _gen_metadata(message) -> dict:
    """Minimal generation diagnostics for the step records: termination status
    and token usage (incl. reasoning tokens) only — completion/reasoning text
    is never recorded.
    """
    metadata = getattr(message, "response_metadata", None)
    if not isinstance(metadata, dict):
        return {}
    usage = metadata.get("token_usage") or {}
    details = usage.get("completion_tokens_details") or {}
    gen = {"finish_reason": metadata.get("finish_reason")}
    if usage.get("completion_tokens") is not None:
        gen["completion_tokens"] = usage["completion_tokens"]
    if details.get("reasoning_tokens") is not None:
        gen["reasoning_tokens"] = details["reasoning_tokens"]
    return gen


def evict_llm_request(model, messages) -> None:
    """Drop the LLM-cache row for exactly this request so the next attempt is
    a real generation.

    Recomputes the key the way LangChain's `_generate_with_cache` does
    (id-stripped message copies, `dumps(...)`, `model._get_llm_string()`).
    A configured cache without an `evict` method fails loudly: silently
    keeping the row would make every retry replay the poisoned value. With no
    cache configured there is nothing to poison — every invoke already
    reaches the model.
    """
    llm_cache = getattr(model, "cache", None)
    if not isinstance(llm_cache, BaseCache):
        llm_cache = get_llm_cache()
    if llm_cache is None:
        return
    evict = getattr(llm_cache, "evict", None)
    if not callable(evict):
        raise RuntimeError(
            "stage validation requires an evictable LLM cache, got "
            f"{type(llm_cache).__name__}"
        )
    normalized = [
        (m.model_copy(update={"id": None}) if getattr(m, "id", None) is not None else m)
        for m in messages
    ]
    evict(dumps(normalized), model._get_llm_string())


def invoke_validated_or_capture(model, messages, stage: StageValidation):
    """`invoke_or_capture` plus stage validation: bounded retries of the
    identical request, each invalid result evicted from the LLM cache first
    so every retry is a real generation.

    Transport exceptions keep the plain explicit-error path; exhaustion
    becomes a terminal validation error (a scored benchmark failure, not an
    outage).
    """
    attempts = max(1, stage.max_attempts)
    label = None
    for _ in range(attempts):
        try:
            message = invoke_with_retry(model, messages)
        except Exception as e:  # the error is frozen into the cache below
            logger.exception("LLM invoke failed; freezing the error into the cache")
            return "", str(e), {}
        label = stage.check(message.content, _finish_reason(message))
        if label is None:
            return message.content, None, _gen_metadata(message)
        # Also runs after the final attempt: no invalid value may survive as
        # the canonical cache entry.
        evict_llm_request(model, messages)
    return "", f"{label} after {attempts} attempts", {}


# Client-side bound on concurrent LLM calls, threaded from `--llm-concurrency`
# through the step functions like every other CLI setting (default 1 = the
# exact sequential path).


@cache
def _llm_pool(max_workers: int) -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="llm")


def invoke_or_capture_many(
    model, calls, llm_concurrency=1, stage: StageValidation | None = None
) -> list[tuple[str, str | None, dict]]:
    """`invoke_or_capture` over a batch of message lists, bounded by
    `llm_concurrency`. `Executor.map` preserves input order, so record
    processing and the JSON write-through stay on the calling thread.

    With a `stage`, completions are stage-validated and invalid ones retried
    on the identical request (`invoke_validated_or_capture`); without it the
    behavior is exactly the plain path."""

    def run_one(messages):
        if stage is None:
            return invoke_or_capture(model, messages)
        return invoke_validated_or_capture(model, messages, stage)

    if llm_concurrency <= 1:
        return [run_one(messages) for messages in calls]
    pool = _llm_pool(llm_concurrency)
    try:
        return list(pool.map(run_one, calls))
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        _llm_pool.cache_clear()
        raise


def _is_validation_error(error: str | None) -> bool:
    """Stage-validation labels share the `invalid_` prefix. They are scored
    benchmark failures, not the systemic outages `TERMINAL_FAILURE_STREAK`
    guards against."""
    return bool(error) and error.startswith("invalid_")


def run_llm_step(
    questions,
    model,
    model_name,
    cache_key,
    build_messages,
    llm_concurrency=1,
    stage: StageValidation | None = None,
):
    """Shared driver for the LLM steps: skip layer, bounded calls, write-through.

    Skip layer: the global LangChain cache when configured — resume replays
    finished questions as cache hits and re-invokes only ids with no cached
    row; otherwise the JSON step cache, the exact upstream behavior. JSON stays
    a complete write-through artifact either way (the completion checks read it).

    `build_messages(i)` returns the message list for `questions[i]`; each step
    keeps its own prompt construction. `stage` opts the step into output
    validation with bounded identical-request retries.
    """
    cache = load_cache(model_name, cache_key)
    skip_json = get_llm_cache() is None
    results: list = [None] * len(questions)
    # Exhausted structural failures are final raw results. Transport/config
    # errors remain resumable, including when PostgreSQL is the normal skip layer.
    todo = [
        i
        for i, q in enumerate(questions)
        if not (
            q["id"] in cache
            and (
                _is_validation_error(cache[q["id"]].get("error"))
                or (skip_json and not cache[q["id"]].get("error"))
            )
        )
    ]
    consecutive_failures = 0
    batch = max(1, llm_concurrency)
    with tqdm(total=len(todo), desc=f"  {cache_key}") as progress:
        for start in range(0, len(todo), batch):
            idxs = todo[start : start + batch]
            contents = invoke_or_capture_many(
                model, [build_messages(i) for i in idxs], llm_concurrency, stage
            )
            for i, (content, error, gen) in zip(idxs, contents, strict=True):
                record = {"id": questions[i]["id"], "content": content}
                if error:
                    record["error"] = error
                if gen:
                    record["gen"] = gen
                results[i] = record
                # Write-through after every item so partial runs are recoverable;
                # identical replays (cache hits) skip the rewrite.
                if cache.get(questions[i]["id"]) != record:
                    cache[questions[i]["id"]] = record
                    save_cache(model_name, cache_key, list(cache.values()))
                # Validation failures are benchmark results, not outage signals.
                consecutive_failures = (
                    consecutive_failures + 1
                    if error and not _is_validation_error(error)
                    else 0
                )
                if consecutive_failures >= TERMINAL_FAILURE_STREAK:
                    raise RuntimeError(
                        f"{cache_key}: {consecutive_failures} consecutive model"
                        " failures — aborting; cached results are preserved"
                    )
            progress.update(len(idxs))
    return [
        r if r is not None else cache[q["id"]]
        for r, q in zip(results, questions, strict=True)
    ]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def cache_path(model_name: str, step: str) -> Path:
    p = CACHE_DIR / model_name
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{step}.json"


def load_cache(model_name: str, step: str) -> dict:
    """Return {id: record} dict, or empty dict if no cache."""
    p = cache_path(model_name, step)
    if p.exists():
        records = json.loads(p.read_text())
        return {r["id"]: r for r in records}
    return {}


class _JSONEncoder(json.JSONEncoder):
    """Handles types returned by psycopg that the default encoder can't serialize."""

    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return super().default(o)


def save_cache(model_name: str, step: str, records: list):
    cache_path(model_name, step).write_text(
        json.dumps(records, indent=2, cls=_JSONEncoder)
    )


def clear_cache(model_name: str, steps):
    """Delete cache files for the given step names (or 'all')."""
    p = CACHE_DIR / model_name
    if not p.exists():
        return
    if steps == ["all"]:
        for f in p.glob("*.json"):
            f.unlink()
            print(f"  Cleared cache: {f.name}")
    else:
        for step in steps:
            f = cache_path(model_name, step)
            if f.exists():
                f.unlink()
                print(f"  Cleared cache: {f.name}")
            else:
                print(f"  No cache to clear: {f.name}")


# ---------------------------------------------------------------------------
# Question loading
# ---------------------------------------------------------------------------


def load_questions(mode: str = "full") -> list:
    """Load benchmark questions, keeping their frozen string ids.

    `smoke` keeps only the first question of each type file — a deterministic
    one-per-type integration subset (28 questions for the full benchmark),
    never benchmark evidence.
    """
    if mode not in ("smoke", "full"):
        raise ValueError(f"unknown mode: {mode!r}")
    files = sorted(glob(str(QUESTIONS_DIR / "*.jsonl")))
    questions = []
    for path in files:
        qtype = Path(path).stem
        with open(path) as f:
            for i, line in enumerate(f):
                if mode == "smoke" and i > 0:
                    break
                if i >= MAX_QUESTIONS_PER_TYPE:
                    break
                q = json.loads(line)
                if not q.get("id"):
                    raise KeyError(
                        f"question id missing in {path}"
                        " — frozen benchmarks require stable ids"
                    )
                q["type"] = qtype
                questions.append(q)
    return questions


# ---------------------------------------------------------------------------
# JSON / math utilities  (carried over from notebooks)
# ---------------------------------------------------------------------------

_BIN_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}
_UNARY_OPS = {ast.UAdd: op.pos, ast.USub: op.neg}
_ALLOWED_CHARS = re.compile(r"^[0-9+\-*/().\s]+$")
MATH_EQ_RE = re.compile(
    r"""(?P<full>(?P<lhs>(?=.*[+\-*/])[0-9+\-*/().\s]*\d)\s*=\s*(?P<rhs>[0-9+\-*/().\s]*\d))"""
    r"""|(?P<expr>(?=.*[+\-*/])[0-9+\-*/().\s]*\d)""",
    re.VERBOSE,
)


def safe_eval(expr: str) -> float:
    expr = expr.strip()
    if not expr or not _ALLOWED_CHARS.fullmatch(expr):
        raise ValueError(f"Invalid expression: {expr!r}")

    def _eval(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN_OPS:
            return _BIN_OPS[type(n.op)](_eval(n.left), _eval(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNARY_OPS:
            return _UNARY_OPS[type(n.op)](_eval(n.operand))
        raise ValueError(f"Unsupported expression: {expr!r}")

    return _eval(ast.parse(expr, mode="eval").body)


def replace_math(text: str) -> str:
    def repl(m):
        try:
            if m.group("full"):
                return " " + str(safe_eval(m.group("lhs").strip()))
            if m.group("expr"):
                return " " + str(safe_eval(m.group("expr").strip()))
        except (ArithmeticError, SyntaxError, TypeError, ValueError):
            pass
        return m.group(0)

    return MATH_EQ_RE.sub(repl, text)


def flatten_if_nested(array):
    if isinstance(array, list) and any(isinstance(i, list) for i in array):
        out = []
        for item in array:
            out.extend(flatten_if_nested(item) if isinstance(item, list) else [item])
        return out
    return array


def extract_json_blocks(text: str, idx: int = -1) -> list:
    matches = re.findall(r"```[\s]*json(.*?)```", text, re.DOTALL)
    blocks = []
    for match in matches:
        try:
            s = match.strip()
            s = replace_math(s)
            s = re.sub(r"\b\d+(?:_\d+)*\b", lambda x: x.group().replace("_", ""), s)
            s = re.sub(r"\b\d+(?:,\d+)*\b", lambda x: x.group().replace(",", ""), s)
            s = re.sub(r"//.*?\n", "", s)
            s = re.sub(r",\s*}", "}", s)
            s = (
                s.replace("""\\\'""", """\'""")
                .replace("""\\&""", """&""")
                .replace("}\njson", "}")
            )
            if re.search(r"}\s*{", s):
                s = re.sub(r"}\s*{", "},\n{", s)
                s = f"[\n{s}\n]"
            convert_area = "acres" in s
            if convert_area:
                s = s.replace(" acres,", ",")
            data = json.loads(s)
            if convert_area and "area" in data:
                data["area"] = data["area"] * 4046.8564224
            blocks.append(data)
        except json.JSONDecodeError as e:
            print(f"  [json parse warning] question {idx}: {e}")
    return flatten_if_nested(blocks)


# ---------------------------------------------------------------------------
# SQL execution
# ---------------------------------------------------------------------------

DB_PARAMS = dict(
    host=os.getenv("PGHOST", "localhost"),
    dbname=os.getenv("PGDATABASE", "osm_ca"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
    port=int(os.getenv("PGPORT", "5432")),
)
SQL_TIMEOUT_MS = 100_000
DEFAULT_SQL_CONCURRENCY = 4


def make_db_conn():
    # autocommit so session-level SETs (read-only, timeout) apply to the very
    # next statement instead of the next transaction
    return psycopg.connect(**DB_PARAMS, row_factory=dict_row, autocommit=True)


def run_sql(sql: str, conn) -> dict:
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {SQL_TIMEOUT_MS}")
            cur.execute("SET default_transaction_read_only = ON")
            cur.execute(sql)
            rows = cur.fetchmany(100)
            return {
                "output": [
                    {k: v for k, v in row.items() if v is not None} for row in rows
                ],
                "error": "",
            }
    except psycopg.Error as e:
        try:
            conn.rollback()
        except psycopg.Error:
            pass
        return {"output": [], "error": str(e)}


def extract_sql_blocks(text: str) -> list:
    return re.findall(r"```[\s]*sql(.*?)```", text, re.DOTALL)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


def step_generate_answers(
    questions,
    model,
    model_name,
    cache_key,
    system_prompt,
    llm_concurrency=1,
    stage: StageValidation | None = None,
):
    """Step: question → text answer."""

    def build_messages(i):
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=questions[i]["question"]),
        ]

    return run_llm_step(
        questions, model, model_name, cache_key, build_messages, llm_concurrency, stage
    )


def step_parse_to_json(
    questions,
    answers,
    parser_model,
    model_name,
    cache_key,
    json_prompt_key,
    llm_concurrency=1,
    stage: StageValidation | None = None,
):
    """Step: question + text answer → JSON answer (always uses local parser model)."""
    base_prompt = load_prompt(json_prompt_key)

    def build_messages(i):
        q, a = questions[i], answers[i]
        if "multi_source1" in q["type"]:
            attr = q["answers"][0].get("multi_source_attribute", "")
            prompt = base_prompt.replace("%OTHER_ATT%", f'"{attr}": string')
        else:
            prompt = base_prompt.replace("%OTHER_ATT%", "")
        return [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Question: {q['question']}\nAnswer: {a['content']}"),
        ]

    return run_llm_step(
        questions,
        parser_model,
        model_name,
        cache_key,
        build_messages,
        llm_concurrency,
        stage,
    )


def step_execute_sql(
    questions,
    sql_answers,
    model_name,
    sql_concurrency: int = DEFAULT_SQL_CONCURRENCY,
):
    """Step: SQL text → database records.

    Execution records include their exact extracted SQL blocks. A question ID
    alone is not a safe cache key because a repaired generation can retain the
    same ID while changing the SQL that must be executed.
    When `sql_concurrency` > 1, queries execute on a bounded thread pool
    with one persistent connection per worker thread.
    """
    cache = load_cache(model_name, "sql_exec")
    results = [None] * len(questions)
    todo = []

    for i, (q, a) in enumerate(zip(questions, sql_answers, strict=False)):
        sql_blocks = extract_sql_blocks(a["content"])
        cached = cache.get(q["id"])
        if cached is not None and cached.get("sql_blocks") == sql_blocks:
            results[i] = cached
        else:
            todo.append((i, q, sql_blocks))

    if not todo:
        return [r for r in results if r is not None]

    dirty = False
    workers = max(1, sql_concurrency)

    if workers <= 1:
        conn = None
        try:
            for i, q, sql_blocks in tqdm(
                todo,
                total=len(todo),
                desc="  sql_exec",
            ):
                if conn is None:
                    conn = make_db_conn()
                records = []
                for sql in sql_blocks:
                    try:
                        records.append(run_sql(sql, conn))
                    except psycopg.OperationalError as e:
                        print(
                            f"\n  [db] connection lost (q {q['id']}): {e} "
                            "— reconnecting"
                        )
                        try:
                            conn.close()
                        except psycopg.Error:
                            pass
                        conn = make_db_conn()
                        records.append(run_sql(sql, conn))
                record = {"id": q["id"], "sql_blocks": sql_blocks, "records": records}
                results[i] = record
                cache[q["id"]] = record
                dirty = True
        finally:
            if conn:
                try:
                    conn.close()
                except psycopg.Error:
                    pass
            if dirty:
                save_cache(model_name, "sql_exec", list(cache.values()))
        return [r for r in results if r is not None]

    # Parallel execution with thread-local persistent connection per worker
    thread_local = threading.local()

    def _exec_one(item):
        idx, q, sql_blocks = item
        conn = getattr(thread_local, "conn", None)
        if conn is None or conn.closed:
            conn = make_db_conn()
            thread_local.conn = conn
        records = []
        for sql in sql_blocks:
            try:
                records.append(run_sql(sql, conn))
            except psycopg.OperationalError as e:
                print(f"\n  [db] connection lost (q {q['id']}): {e} — reconnecting")
                try:
                    conn.close()
                except psycopg.Error:
                    pass
                conn = make_db_conn()
                thread_local.conn = conn
                records.append(run_sql(sql, conn))
        return idx, {"id": q["id"], "sql_blocks": sql_blocks, "records": records}

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for idx, record in tqdm(
                pool.map(_exec_one, todo),
                total=len(todo),
                desc="  sql_exec",
            ):
                results[idx] = record
                cache[record["id"]] = record
                dirty = True
    finally:
        if dirty:
            save_cache(model_name, "sql_exec", list(cache.values()))

    return [r for r in results if r is not None]


def step_answer_from_records(
    questions,
    sql_answers,
    sql_outputs,
    model,
    model_name,
    llm_concurrency=1,
    stage: StageValidation | None = None,
):
    """Step: question + SQL records → text answer."""
    base_prompt = load_prompt("sql_answer")

    def build_messages(i):
        records_text = json.dumps(
            sql_outputs[i].get("records", []), indent=2, cls=_JSONEncoder
        )
        return [
            SystemMessage(content=base_prompt + records_text),
            HumanMessage(content=questions[i]["question"]),
        ]

    return run_llm_step(
        questions,
        model,
        model_name,
        "sql_answer",
        build_messages,
        llm_concurrency,
        stage,
    )


# ---------------------------------------------------------------------------
# Evaluation  (unchanged from notebooks)
# ---------------------------------------------------------------------------


def get_recursive(data, search_key):
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k == search_key and isinstance(v, str):
                out.append(v)
            else:
                out.extend(get_recursive(v, search_key))
    elif isinstance(data, list):
        for item in data:
            out.extend(get_recursive(item, search_key))
    return out


def improved_f1(new_f1, scores):
    return "F1" not in scores or new_f1 > scores["F1"]


def evaluate_answers(
    questions, answers, parsed_answers, evaluate_mod, geocoder, geod, prefix
):
    text_eval = []
    parsed_eval = []

    for i, q in enumerate(questions):
        a = answers[i]
        text_answer = a["content"]
        parsed_answer = parsed_answers[i]

        # --- text evaluation ---
        key = ""
        if "multi_source1" in q["type"]:
            key = "multi_source_long_answer"
        elif "name" in q["type"]:
            key = "name"
        elif "loc" in q["type"]:
            key = "address"
        elif "angle" in q["type"]:
            key = "angle_description"
        elif "area" in q["type"]:
            key = "area"
        elif "length" in q["type"]:
            key = "length"
        elif "count" in q["type"]:
            key = "count"
        elif "distance" in q["type"]:
            key = "distance"

        true_answers = []
        for ans in q["answers"]:
            v = evaluate_mod.get_osm_value(ans, key)
            if v is None:
                continue
            if key in ("area", "length", "count", "distance"):
                v = num2words(v)
            if key == "area":
                v += " meters squared"
            elif key in ("length", "distance"):
                v += " meters"
            true_answers.append(v)

        if text_answer and text_answer.strip() and true_answers:
            P, R, F1 = evaluate_mod.evaluate_entity_names(
                text_answer, "\n".join(true_answers)
            )
            text_eval.append({"attempted": True, "P": P, "R": R, "F1": F1})
        else:
            text_eval.append({"attempted": False, "P": 0, "R": 0, "F1": 0})

        # --- parsed evaluation ---
        scores = {"attempted": False}
        if "multi_source1" in q["type"]:
            for ans in q["answers"]:
                v = evaluate_mod.get_osm_value(ans, "multi_source_answer")
                if v is None:
                    continue
                for p in parsed_answer:
                    pred = p.get(ans["multi_source_attribute"], None)
                    if not pred:
                        continue
                    P, R, F1 = evaluate_mod.evaluate_entity_names(pred, v)
                    if improved_f1(F1, scores):
                        scores = {"attempted": True, "P": P, "R": R, "F1": F1}
        elif "name" in q["type"]:
            for ans in q["answers"]:
                v = evaluate_mod.get_osm_value(ans, "name")
                if v is None:
                    continue
                for p in parsed_answer:
                    preds = get_recursive(p, "name")
                    if not preds:
                        continue
                    P, R, F1 = evaluate_mod.evaluate_entity_names(preds[0], v)
                    if improved_f1(F1, scores):
                        scores = {"attempted": True, "P": P, "R": R, "F1": F1}
        elif "loc" in q["type"]:
            for ans in q["answers"]:
                v = evaluate_mod.get_osm_value(ans, "address")
                loc = evaluate_mod.get_osm_value(ans, "location")
                if v is None:
                    continue
                for p in parsed_answer:
                    preds = get_recursive(p, "address")
                    if not preds:
                        continue
                    pred = preds[0]
                    P, R, F1 = evaluate_mod.evaluate_entity_names(pred, v)
                    if improved_f1(F1, scores):
                        scores.update({"attempted": True, "P": P, "R": R, "F1": F1})
                    pred_loc = evaluate_mod.get_location_by_address(geocoder, pred)
                    if pred_loc is None:
                        continue
                    dist_err = evaluate_mod.evaluate_location(geod, [pred_loc], [loc])[
                        0
                    ]
                    dist_err = min(dist_err / DISTANCE_ERROR_NORM_M, 1.0)
                    if dist_err < scores.get("distance_error", float("inf")):
                        scores["distance_error"] = dist_err
        elif "angle" in q["type"]:
            for ans in q["answers"]:
                angle = evaluate_mod.get_osm_value(ans, "angle")
                angle_desc = evaluate_mod.get_osm_value(ans, "angle_description")
                if angle is None:
                    continue
                for p in parsed_answer:
                    pred_angle = p.get("azimuth_angle", None)
                    try:
                        pred_angle = int(pred_angle)
                    except (TypeError, ValueError):
                        continue
                    pred_desc = evaluate_mod.get_angle_desc(pred_angle)
                    if not pred_desc:
                        continue
                    P, R, F1 = evaluate_mod.evaluate_entity_names(pred_desc, angle_desc)
                    if improved_f1(F1, scores):
                        scores.update({"attempted": True, "P": P, "R": R, "F1": F1})
                    angle_err = evaluate_mod.evaluate_angle([pred_angle], [angle])[0]
                    if angle_err < scores.get("angle_error", float("inf")):
                        scores["angle_error"] = angle_err
        elif q["type"].endswith(("area", "length", "count", "distance")):
            mkey = next(
                k for k in ("area", "length", "count", "distance") if k in q["type"]
            )
            for ans in q["answers"]:
                v = evaluate_mod.get_osm_value(ans, mkey)
                if v is None:
                    continue
                for p in parsed_answer:
                    pred_v = p.get(mkey, None)
                    try:
                        pred_v = int(pred_v)
                    except (TypeError, ValueError):
                        continue
                    rel_err = evaluate_mod.evaluate_measurement(pred_v, v)
                    if rel_err < scores.get("relative_error", float("inf")):
                        scores["relative_error"] = rel_err
                        scores["attempted"] = True

        parsed_eval.append(scores)

    return text_eval, parsed_eval


def save_eval(text_eval, parsed_eval, questions, model_name, prefix):
    # Model tags like "org/repo:quant" contain "/" — flatten so the CSV path
    # stays a file inside ROOT instead of a path into a missing directory.
    model_name = model_name.replace("/", "_")
    df_text = pd.DataFrame(text_eval)
    df_text["type"] = [q["type"] for q in questions]
    df_text["id"] = [q["id"] for q in questions]
    df_text.to_csv(ROOT / f"{model_name}_{prefix}_text_eval.csv", index=False)

    df_parsed = pd.DataFrame(parsed_eval)
    df_parsed["type"] = [q["type"] for q in questions]
    df_parsed["id"] = [q["id"] for q in questions]

    # Enforce: unattempted rows always have worst-case scores
    not_att = ~df_parsed["attempted"].astype(bool)
    for col in ("P", "R", "F1"):
        if col in df_parsed:
            df_parsed.loc[df_parsed[col].isna(), col] = 0
            df_parsed.loc[not_att, col] = 0
    for col in ("distance_error", "angle_error", "relative_error"):
        if col in df_parsed:
            df_parsed.loc[df_parsed[col].isna(), col] = 1.0
            df_parsed.loc[not_att, col] = 1.0

    # Cap error scores at 1.0
    for col in ("relative_error", "distance_error", "angle_error"):
        if col in df_parsed:
            df_parsed[col] = df_parsed[col].clip(upper=1.0)

    df_parsed.to_csv(ROOT / f"{model_name}_{prefix}_parsed_eval.csv", index=False)
    print(f"  Saved eval CSVs: {model_name}_{prefix}_*.csv")


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def step_rag_answers(questions, model, model_name, vector_store, k=10):
    """Step: question + retrieved OSM records → text answer."""
    base_prompt = load_prompt("rag_answer")
    cache = load_cache(model_name, "rag_answer")
    results = []
    for q in tqdm(questions, desc="  rag_answer"):
        if q["id"] in cache:
            results.append(cache[q["id"]])
            continue
        docs = vector_store.similarity_search(q["question"], k=k)
        records = "\n".join(d.page_content for d in docs)
        messages = [
            SystemMessage(content=base_prompt + records),
            HumanMessage(content=q["question"]),
        ]
        content = invoke_with_retry(model, messages).content
        record = {"id": q["id"], "content": content}
        results.append(record)
        cache[q["id"]] = record
        save_cache(model_name, "rag_answer", list(cache.values()))
    return results


def run_direct(
    questions,
    model,
    parser_model,
    model_name,
    evaluate_mod,
    geocoder,
    geod,
    llm_concurrency=1,
):
    print("\n[direct baseline]")

    # Step 1: generate answers
    answers = step_generate_answers(
        questions,
        model,
        model_name,
        cache_key="direct_answer",
        system_prompt=load_prompt("direct_answer"),
        llm_concurrency=llm_concurrency,
    )

    # Step 2: parse to JSON
    json_answers = step_parse_to_json(
        questions,
        answers,
        parser_model,
        model_name,
        cache_key="direct_json_parse",
        json_prompt_key="direct_json_parse",
        llm_concurrency=llm_concurrency,
    )

    # Step 3: extract JSON blocks
    parsed_answers = [
        extract_json_blocks(a["content"], i) for i, a in enumerate(json_answers)
    ]

    # Evaluation
    text_eval, parsed_eval = evaluate_answers(
        questions,
        answers,
        parsed_answers,
        evaluate_mod,
        geocoder,
        geod,
        prefix="direct",
    )
    save_eval(text_eval, parsed_eval, questions, model_name, prefix="direct")


def run_text2sql(
    questions,
    model,
    parser_model,
    model_name,
    evaluate_mod,
    geocoder,
    geod,
    llm_concurrency=1,
):
    print("\n[text2sql baseline]")

    # Step 1: generate SQL
    sql_answers = step_generate_answers(
        questions,
        model,
        model_name,
        cache_key="sql_generate",
        system_prompt=load_prompt("sql_generate"),
        llm_concurrency=llm_concurrency,
    )

    # Step 2: execute SQL
    sql_outputs = step_execute_sql(
        questions,
        sql_answers,
        model_name,
        sql_concurrency=max(llm_concurrency, DEFAULT_SQL_CONCURRENCY),
    )

    # Step 3: generate answer from records
    answers = step_answer_from_records(
        questions,
        sql_answers,
        sql_outputs,
        model,
        model_name,
        llm_concurrency=llm_concurrency,
    )

    # Step 4: parse to JSON
    json_answers = step_parse_to_json(
        questions,
        answers,
        parser_model,
        model_name,
        cache_key="sql_json_parse",
        json_prompt_key="sql_json_parse",
        llm_concurrency=llm_concurrency,
    )

    # Step 5: extract JSON blocks
    parsed_answers = [
        extract_json_blocks(a["content"], i) for i, a in enumerate(json_answers)
    ]

    # Evaluation
    text_eval, parsed_eval = evaluate_answers(
        questions,
        answers,
        parsed_answers,
        evaluate_mod,
        geocoder,
        geod,
        prefix="text2sql",
    )
    save_eval(text_eval, parsed_eval, questions, model_name, prefix="text2sql")


WIKIPEDIA_CORPUS = ROOT / "wikipedia_corpus.jsonl"

EMBEDDINGS_MODELS = {
    # name            : (provider, model_id)
    "minilm": ("hf", "all-MiniLM-L6-v2"),  # fast, local, no Ollama needed
    "nomic": ("ollama", "nomic-embed-text"),  # fast Ollama embedding model
    "qwen3.5": ("ollama", "qwen3.5:cloud"),  # original (slow)
    "openai-small": ("openai", "text-embedding-3-small"),
}


def build_embeddings(name: str):
    provider, model_id = EMBEDDINGS_MODELS[name]
    if provider == "hf":
        return HuggingFaceEmbeddings(model_name=model_id)
    if provider == "ollama":
        base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return OllamaEmbeddings(model=model_id, base_url=base_url)
    if provider == "openai":
        return OpenAIEmbeddings(model=model_id)
    raise ValueError(f"Unknown embeddings provider: {provider}")


def _vectorstore_dir(embeddings_name: str) -> Path:
    return ROOT / f"osm_vectorstore_{embeddings_name}"


def _build_vectorstore(embeddings, store_dir: Path):
    """Build the Chroma vector store from OSM questions + Wikipedia corpus.
    Only called when the store does not exist yet."""
    print("  Building vector store (this runs once)…")

    def extract_objects_with_geometry(data, result=None):
        if result is None:
            result = []
        if isinstance(data, dict):
            if "geometry" in data:
                result.append(data)
            for v in data.values():
                extract_objects_with_geometry(v, result)
        elif isinstance(data, list):
            for item in data:
                extract_objects_with_geometry(item, result)
        return result

    corpus = []
    for path in sorted(glob(str(QUESTIONS_DIR / "*.jsonl"))):
        with open(path) as f:
            for _ in range(100):
                line = f.readline()
                if not line:
                    break
                q = json.loads(line)
                objs = extract_objects_with_geometry(q)
                corpus += [
                    {k: o[k] for k in o if o[k] is not None and k != "geometry"}
                    for o in objs
                ]

    if WIKIPEDIA_CORPUS.exists():
        with open(WIKIPEDIA_CORPUS) as f:
            for line in f:
                if line.strip():
                    corpus.append(json.loads(line)["data"])

    print(f"  Corpus size: {len(corpus)} documents")

    vector_store = Chroma(
        collection_name="osm",
        embedding_function=embeddings,
        persist_directory=str(store_dir),
    )

    batch, ids, i = [], [], 0
    for obj in tqdm(corpus, desc="  embedding"):
        batch.append(Document(page_content=json.dumps(obj)))
        ids.append(str(i))
        i += 1
        if len(batch) == EMBEDDING_BATCH_SIZE:
            vector_store.add_documents(documents=batch, ids=ids)
            batch, ids = [], []
    if batch:
        vector_store.add_documents(documents=batch, ids=ids)

    print(f"  Vector store built: {i} documents → {store_dir}")
    return vector_store


def _load_vectorstore(embeddings, store_dir: Path):
    return Chroma(
        collection_name="osm",
        embedding_function=embeddings,
        persist_directory=str(store_dir),
    )


def run_rag(
    questions,
    model,
    parser_model,
    model_name,
    evaluate_mod,
    geocoder,
    geod,
    embeddings_name: str = "minilm",
):
    print(f"\n[rag baseline]  embeddings={embeddings_name}")

    embeddings = build_embeddings(embeddings_name)
    store_dir = _vectorstore_dir(embeddings_name)

    # Build store only if it doesn't exist yet; otherwise load the existing one
    store_exists = store_dir.exists() and any(store_dir.iterdir())
    if store_exists:
        vector_store = _load_vectorstore(embeddings, store_dir)
        print(f"  Vector store loaded: {vector_store._collection.count()} documents")
    else:
        vector_store = _build_vectorstore(embeddings, store_dir)
        print(f"  Vector store ready: {vector_store._collection.count()} documents")

    # Step 1: retrieve + answer
    answers = step_rag_answers(questions, model, model_name, vector_store)

    # Step 2: parse to JSON
    json_answers = step_parse_to_json(
        questions,
        answers,
        parser_model,
        model_name,
        cache_key="rag_json_parse",
        json_prompt_key="rag_json_parse",
    )

    # Step 3: extract JSON blocks
    parsed_answers = [
        extract_json_blocks(a["content"], i) for i, a in enumerate(json_answers)
    ]

    # Evaluation
    text_eval, parsed_eval = evaluate_answers(
        questions, answers, parsed_answers, evaluate_mod, geocoder, geod, prefix="rag"
    )
    save_eval(text_eval, parsed_eval, questions, model_name, prefix="rag")


# ---------------------------------------------------------------------------
# Shuffled (random) baseline
# ---------------------------------------------------------------------------


def _rebuild_query_shuffled(original_sql: str, q_type: str) -> str:
    """
    Build a randomised LIMIT 1 query keeping only simple tag=value predicates.

    Instead of trying to parse AND/OR trees (which breaks on BETWEEN x AND y),
    we extract only bare equality / ILIKE predicates with quoted string values.
    These are the category filters (amenity='cafe', cuisine ILIKE '%Korean%', etc.)
    — exactly what we want for a random pick.
    """
    # Determine the main table from the FROM clause (ignore CTEs)
    with_names = set(re.findall(r"\b(\w+)\b\s+AS\s*\(", original_sql, re.IGNORECASE))
    from_m = re.search(
        r"\bFROM\s+([\w,\s]+?)(?:\s+WHERE|\s+ORDER|\s+GROUP|\s+LIMIT|;|$)",
        original_sql,
        re.IGNORECASE,
    )
    table = "pois"
    if from_m:
        tables = [t.strip().split()[0] for t in from_m.group(1).split(",")]
        real = [t for t in tables if t and t not in with_names]
        if real:
            table = real[0]

    # Extract only simple   col = 'value'   or   col ILIKE 'value'   predicates.
    # This safely ignores ST_ functions, BETWEEN, numeric fragments, etc.
    simple_preds = re.findall(
        r"\b\w+\s*(?:=|ILIKE|LIKE)\s*\'[^\']+\'",
        original_sql,
        re.IGNORECASE,
    )

    predicates = list(dict.fromkeys(simple_preds))  # deduplicate, preserve order

    if "loc" in q_type:
        predicates.append("addr_city IS NOT NULL")

    where = (" WHERE " + " AND ".join(predicates)) if predicates else ""
    return f"SELECT * FROM {table}{where} ORDER BY RANDOM() LIMIT 1"


def _random_angle() -> dict:
    directions = [
        (
            "north",
            [random.uniform(0.0, 22.5), random.uniform(337.5, 360.0)][
                random.randint(0, 1)
            ],
        ),
        ("northeast", random.uniform(22.5, 67.5)),
        ("east", random.uniform(67.5, 112.5)),
        ("southeast", random.uniform(112.5, 157.5)),
        ("south", random.uniform(157.5, 202.5)),
        ("southwest", random.uniform(202.5, 247.5)),
        ("west", random.uniform(247.5, 292.5)),
        ("northwest", random.uniform(292.5, 337.5)),
    ]
    name, angle = random.choice(directions)
    return {"angle_description": name, "angle": angle}


def _random_multi_source_value(attribute: str):
    """Generate a plausible random value for a multi_source attribute."""
    generators = {
        "Architect": lambda: f"Architect {random.randint(1, 999)}",
        "Built": lambda: str(random.randint(1800, 2025)),
        "Created": lambda: str(random.randint(1800, 2025)),
        "Established": lambda: str(random.randint(1700, 2025)),
        "Director": lambda: f"Director {random.randint(1, 999)}",
        "Founder": lambda: f"Founder {random.randint(1, 999)}",
        "Headquarters": lambda: f"City {random.randint(1, 999)}",
        "Opened": lambda: str(random.randint(1800, 2025)),
        "Opening date": lambda: str(random.randint(1800, 2025)),
        "Affiliated university": lambda: f"University {random.randint(1, 99)}",
        "Emergency department": lambda: random.choice(["Yes", "No"]),
        "Helipad": lambda: random.choice(["Yes", "No"]),
        "Date opened": lambda: str(random.randint(1900, 2025)),
        "Capacity": lambda: str(random.randint(50, 100_000)),
        "Former names": lambda: f"Old Name {random.randint(1, 99)}",
        "Motto": lambda: "A random motto",
        "Mascot": lambda: f"Mascot{random.randint(1, 99)}",
        "Nickname": lambda: f"Nick{random.randint(1, 99)}",
        "Designed by": lambda: f"Designer {random.randint(1, 99)}",
        "Nearest\xa0city": lambda: f"City {random.randint(1, 99)}",
    }
    gen = generators.get(attribute)
    return gen() if gen else f"Unknown {attribute}"


def run_shuffled(
    questions,
    parser_model,
    model_name,
    evaluate_mod,
    geocoder,
    geod,
    llm_concurrency=1,
):
    print("\n[shuffled baseline]")

    # The answer-generation step is model-independent (pure SQL + random),
    # so cache it under the fixed key "shuffled" regardless of parser model.
    SHUFFLED_CACHE_MODEL = "shuffled"
    cache = load_cache(SHUFFLED_CACHE_MODEL, "shuffled_answer")

    answers = []
    needs_db = any(
        q["id"] not in cache and ("name" in q["type"] or "loc" in q["type"])
        for q in questions
    )
    conn = make_db_conn() if needs_db else None

    for q in tqdm(questions, desc="  shuffled_answers"):
        if q["id"] in cache:
            answers.append(cache[q["id"]])
            continue

        q_type = q["type"]
        element = []

        if "multi_source1" in q_type:
            # Must be checked before the generic "name" branch because
            # knn+name+multi_source1 contains "name" but needs its own handler.
            att = q["answers"][0].get("multi_source_attribute", "")
            element = [
                {
                    "multi_source_long_answer": att
                    + " "
                    + str(_random_multi_source_value(att))
                }
            ]

        elif "name" in q_type or "loc" in q_type:
            sql = _rebuild_query_shuffled(q["sql"], q_type).replace("\x01", "")
            result = run_sql(sql, conn)
            if result["error"]:
                tqdm.write(f"  [SQL error] q{q['id']}: {result['error'][:120]}")
            element = result["output"]

        elif "angle" in q_type:
            element = [_random_angle()]

        elif "area" in q_type:
            element = [{"area": random.randint(1, 10**10)}]

        elif "length" in q_type:
            element = [{"length": random.randint(1, 10**10)}]

        elif "distance" in q_type:
            element = [{"distance": random.randint(1, 10**10)}]

        elif "count" in q_type:
            element = [{"count": random.randint(1, 10**4)}]

        # Convert element to text
        key_map = [
            ("multi_source1", "multi_source_long_answer"),
            ("name", "name"),
            ("loc", "address"),
            ("angle", "angle_description"),
            ("area", "area"),
            ("length", "length"),
            ("count", "count"),
            ("distance", "distance"),
        ]
        key = next((k for tag, k in key_map if tag in q_type), "")

        parts = []
        for row in element:
            v = evaluate_mod.get_osm_value(row, key)
            if v is None:
                continue
            if key in ("area", "length", "count", "distance"):
                v = num2words(v)
            if key == "area":
                v += " meters squared"
            elif key in ("length", "distance"):
                v += " meters"
            parts.append(v)
            if (
                len(parts) >= MAX_SHUFFLED_PARTS
                or sum(len(p) for p in parts) > MAX_SHUFFLED_ANSWER_CHARS
            ):
                break

        record = {"id": q["id"], "content": "\n".join(parts)}
        answers.append(record)
        cache[q["id"]] = record
        save_cache(SHUFFLED_CACHE_MODEL, "shuffled_answer", list(cache.values()))

    if conn:
        conn.close()

    # JSON-parse step (cached under parser model_name since it depends on the parser)
    json_answers = step_parse_to_json(
        questions,
        answers,
        parser_model,
        model_name,
        cache_key="shuffled_json_parse",
        json_prompt_key="direct_json_parse",
        llm_concurrency=llm_concurrency,
    )

    parsed_answers = [
        extract_json_blocks(a["content"], i) for i, a in enumerate(json_answers)
    ]

    text_eval, parsed_eval = evaluate_answers(
        questions,
        answers,
        parsed_answers,
        evaluate_mod,
        geocoder,
        geod,
        prefix="shuffled",
    )
    save_eval(text_eval, parsed_eval, questions, model_name, prefix="shuffled")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(description="SpatialQA baseline runner")
    parser.add_argument(
        "--model",
        required=True,
        help=(
            "Model for generation: 'sonnet4.6', 'haiku4.5', 'gpt4o', "
            "or any local Ollama tag (e.g. qwen3.5:9b, llama3.1:8b)"
        ),
    )
    parser.add_argument(
        "--baseline",
        default="all",
        choices=["direct", "text2sql", "rag", "shuffled", "all"],
        help="Which baseline(s) to run",
    )
    parser.add_argument(
        "--parser-model",
        default=None,
        help="Model for the JSON-parsing step (default: same as --model)",
    )
    parser.add_argument(
        "--mode",
        default="full",
        choices=["smoke", "full"],
        help=(
            "smoke = first question per type (8 total, integration evidence only); "
            "full = entire benchmark"
        ),
    )
    parser.add_argument(
        "--embeddings",
        default="nomic",
        choices=list(EMBEDDINGS_MODELS.keys()),
        help="Embedding model for the RAG vector store (default: nomic)",
    )
    parser.add_argument(
        "--ollama-url",
        default=None,
        help=(
            "Base URL for Ollama. "
            "Overrides the OLLAMA_HOST environment variable. "
            "Default: https://ollama.com or use http://localhost:11434"
        ),
    )
    parser.add_argument(
        "--ollama-key",
        default=None,
        help=(
            "API key for Ollama cloud. "
            "Overrides the OLLAMA_API_KEY environment variable."
        ),
    )
    parser.add_argument(
        "--clear-cache",
        default="",
        help=(
            "Comma-separated cache steps to clear before running, or 'all'. "
            "Steps: direct_answer, direct_json_parse, "
            "sql_generate, sql_exec, sql_answer, sql_json_parse, "
            "rag_answer, rag_json_parse"
        ),
    )
    parser.add_argument(
        "--llm-concurrency",
        type=int,
        required=True,
        help=(
            "Client-side bound on concurrent LLM calls, shared by all LLM "
            "steps; set it to what the serving endpoint's throughput allows."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # If --ollama-url / --ollama-key provided, set env vars so the ollama
    # client picks them up
    if args.ollama_url:
        os.environ["OLLAMA_HOST"] = args.ollama_url
    if args.ollama_key:
        os.environ["OLLAMA_API_KEY"] = args.ollama_key

    # Clear cache if requested
    if args.clear_cache:
        steps = [s.strip() for s in args.clear_cache.split(",")]
        print(f"Clearing cache for model={args.model}, steps={steps}")
        clear_cache(args.model, steps)

    print(f"Model: {args.model}  |  Baseline: {args.baseline}")

    # Build models
    model = build_model(args.model)
    parser_model = build_parser_model(args.parser_model or args.model)

    # `ChatOpenAI` itself is not a context manager; its public root clients
    # are. Closing them on Ctrl-C interrupts blocked HTTP workers so Python
    # does not wait for ThreadPoolExecutor requests before exiting.
    model_clients = ExitStack()
    for llm in (model, parser_model):
        if isinstance(llm, ChatOpenAI):
            model_clients.enter_context(llm.root_client)

    # Load questions
    questions = load_questions(mode=args.mode)
    print(f"Loaded {len(questions)} questions from {QUESTIONS_DIR}")

    # Load evaluate module fresh; the package-qualified name keeps a single
    # module object shared with the Vietnamese patch layer.
    evaluate_mod = importlib.import_module(f"{__package__}.evaluate")
    importlib.reload(evaluate_mod)

    geocoder = Nominatim(user_agent="SpatialQA_baseline")
    geod = Geod(ellps="WGS84")

    # Run baseline(s)
    with model_clients:
        if args.baseline in ("direct", "all"):
            run_direct(
                questions,
                model,
                parser_model,
                args.model,
                evaluate_mod,
                geocoder,
                geod,
                llm_concurrency=args.llm_concurrency,
            )

        if args.baseline in ("text2sql", "all"):
            run_text2sql(
                questions,
                model,
                parser_model,
                args.model,
                evaluate_mod,
                geocoder,
                geod,
                llm_concurrency=args.llm_concurrency,
            )

        if args.baseline in ("rag", "all"):
            run_rag(
                questions,
                model,
                parser_model,
                args.model,
                evaluate_mod,
                geocoder,
                geod,
                embeddings_name=args.embeddings,
            )

        if args.baseline in ("shuffled", "all"):
            run_shuffled(
                questions,
                parser_model,
                args.model,
                evaluate_mod,
                geocoder,
                geod,
                llm_concurrency=args.llm_concurrency,
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
