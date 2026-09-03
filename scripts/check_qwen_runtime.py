"""Verify Qwen routing and non-thinking output before official inference."""

import argparse
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RUNTIME = "unsloth/Qwen3.5-9B-GGUF:Q4_K_XL"
HF_REPO = "unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL"
ORNITH = "ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"
ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_DIR = ROOT / "generator" / "questions_vi"
DIRECT_PROMPT = ROOT / "baselines" / "baseline_prompts" / "direct_answer_vi.txt"
EXPECTED_TIDS = 28
MAX_WORKERS = 4


def _model(models: list[dict], model_id: str) -> dict:
    model = next((item for item in models if item.get("id") == model_id), None)
    if model is None:
        raise SystemExit(f"runtime alias not advertised: {model_id}")
    return model


def _arg_value(server_args: list[str], flag: str) -> str | None:
    try:
        return server_args[server_args.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _check_presets(models: list[dict]) -> None:
    qwen_args = _model(models, RUNTIME).get("status", {}).get("args", [])
    if _arg_value(qwen_args, "--hf-repo") != HF_REPO:
        raise SystemExit(f"{RUNTIME} does not resolve to {HF_REPO}")
    if _arg_value(qwen_args, "--reasoning") != "off":
        raise SystemExit(f"{RUNTIME} is missing --reasoning off")
    try:
        template_kwargs = json.loads(
            _arg_value(qwen_args, "--chat-template-kwargs") or "{}"
        )
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid Qwen chat-template-kwargs: {error}") from error
    if template_kwargs.get("enable_thinking") is not False:
        raise SystemExit(f"{RUNTIME} does not set enable_thinking=false")

    ornith_args = _model(models, ORNITH).get("status", {}).get("args", [])
    if _arg_value(ornith_args, "--hf-repo") != ORNITH:
        raise SystemExit(f"Ornith does not resolve to {ORNITH}")
    leaked = [
        flag
        for flag in ("--reasoning", "--chat-template-kwargs")
        if flag in ornith_args
    ]
    if leaked:
        raise SystemExit(f"Qwen-only options leaked into Ornith: {', '.join(leaked)}")


def _smoke_questions() -> list[dict]:
    questions = []
    for path in sorted(QUESTIONS_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as file:
            question = next((json.loads(line) for line in file if line.strip()), None)
        if question is None:
            raise SystemExit(f"empty frozen question file: {path}")
        questions.append(question)
    if len(questions) != EXPECTED_TIDS:
        raise SystemExit(
            f"expected {EXPECTED_TIDS} frozen TID probes, found {len(questions)}"
        )
    return questions


def _probe(completions_url: str, system_prompt: str, question: dict) -> str:
    payload = {
        "model": RUNTIME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question["question"]},
        ],
        "temperature": 0,
        "max_tokens": 4096,
    }
    request = urllib.request.Request(
        completions_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        result = json.load(response)

    qid = question["id"]
    if result.get("model") != RUNTIME:
        raise RuntimeError(f"{qid}: routed to {result.get('model')!r}, not {RUNTIME}")
    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"{qid}: response has no choices")
    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"{qid}: final content is empty")
    if choice.get("finish_reason") == "length":
        raise RuntimeError(f"{qid}: finish_reason=length")
    for key in ("reasoning_content", "reasoning"):
        value = message.get(key)
        if value and str(value).strip():
            raise RuntimeError(f"{qid}: non-empty {key}")
    if re.search(r"</?think\b", content, re.IGNORECASE):
        raise RuntimeError(f"{qid}: thinking markup leaked into final content")
    return qid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models_url")
    args = parser.parse_args()

    with urllib.request.urlopen(args.models_url, timeout=10) as response:
        models = json.load(response).get("data", [])
    _check_presets(models)

    suffix = "/v1/models"
    if not args.models_url.rstrip("/").endswith(suffix):
        raise SystemExit(f"models_url must end with {suffix}")
    completions_url = (
        args.models_url.rstrip("/").removesuffix(suffix) + "/v1/chat/completions"
    )
    questions = _smoke_questions()
    system_prompt = DIRECT_PROMPT.read_text(encoding="utf-8")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        checked = list(
            pool.map(
                lambda question: _probe(completions_url, system_prompt, question),
                questions,
            )
        )

    print(f"[INFO] {RUNTIME} -> {HF_REPO}")
    print(f"[INFO] Qwen non-thinking router preflight: {len(checked)}/28 passed")


if __name__ == "__main__":
    main()
