"""Completion seals for official baseline runs."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEAL_VERSION = 2
EVALUATION_SEAL_VERSION = 2
EVALUATOR_ID = "vigsqa-gsqa-v3"
EVALUATOR_VERSION = 2
EVALUATION_PARSER_MODEL = "ornith-ai/Ornith-1.5-9B-NVFP4"
EVALUATION_PARSER_PROMPT = "direct_json_parse_vi.txt"
EVALUATION_PARSER_MAX_ATTEMPTS = 3
EVALUATION_PARSER_PROFILE = {
    "temperature": 1.0,
    "top_p": 0.95,
    "presence_penalty": 1.5,
    "seed": 42,
    "max_completion_tokens": 32768,
    "extra_body": {"top_k": 20, "min_p": 0.0, "repetition_penalty": 1.0},
}
STEPS = {
    "direct": ("direct_answer",),
    "text2sql": ("sql_generate", "sql_exec", "sql_answer"),
}
PROMPT_FILES = (
    "direct_answer_vi.txt",
    "text2sql_generate_vi.txt",
    "text2sql_answer_vi.txt",
)


def _sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _shell_value(path: Path, name: str) -> str:
    match = re.search(rf'^{re.escape(name)}="([^"]+)"$', path.read_text(), re.MULTILINE)
    if not match:
        raise ValueError(f"could not read {name} from {path}")
    return match.group(1)


def _current_identity() -> dict:
    questions = ROOT / "generator" / "questions_vi"
    dataset = json.loads((questions / "MANIFEST.json").read_text())
    prompt_dir = ROOT / "baselines" / "baseline_prompts"
    prompt_hash = hashlib.sha256()
    for name in PROMPT_FILES:
        prompt_hash.update((prompt_dir / name).read_bytes())
    restore_db = ROOT / "scripts" / "restore_database.sh"
    return {
        "dataset": {
            "version": dataset["version"],
            "sha256": dataset["dataset_sha256"],
        },
        "prompt_sha256": prompt_hash.hexdigest(),
        "reference_data": {
            "osm_url": _shell_value(ROOT / "scripts" / "download_osm.sh", "OSM_URL"),
            "database_asset_url": _shell_value(restore_db, "DB_ASSET_URL"),
            "database_asset_sha256": _shell_value(restore_db, "DB_ASSET_SHA256"),
        },
    }


def _run_dir(model: str, prompt_sha256: str) -> Path:
    return ROOT / "baselines" / "cache_vi" / f"pv-{prompt_sha256[:8]}" / model


def create_seal(g6_manifest: dict) -> Path:
    """Atomically create a seal from a successful G6 manifest."""
    if g6_manifest.get("g6_passed") is not True:
        raise ValueError("a seal requires a successful G6 result")
    model = g6_manifest["model"]
    baseline = g6_manifest["baseline"]
    artifacts = g6_manifest["artifact_sha256"]
    if baseline not in STEPS or set(artifacts) != set(STEPS[baseline]):
        raise ValueError(f"unexpected artifacts for baseline {baseline!r}")

    identity = _current_identity()
    dataset = g6_manifest["dataset_manifest"]
    if identity["dataset"] != {
        "version": dataset["version"],
        "sha256": dataset["dataset_sha256"],
    }:
        raise ValueError("G6 dataset identity no longer matches the repository")
    if g6_manifest["prompt_version"] != identity["prompt_sha256"][:8]:
        raise ValueError("G6 prompt identity no longer matches the repository")

    seal = {
        "seal_version": SEAL_VERSION,
        "model": model,
        "baseline": baseline,
        **identity,
        "artifacts": {step: artifacts[step] for step in STEPS[baseline]},
        "git_commit": g6_manifest["git_commit"],
        "completed_at": g6_manifest["finished"],
    }
    path = _run_dir(model, identity["prompt_sha256"]) / f"{baseline}.seal.json"
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n")
    part.replace(path)
    return path


def validate_seal(model: str, baseline: str) -> tuple[bool, str]:
    """Validate a stable seal against current inputs and raw artifacts."""
    try:
        if baseline not in STEPS:
            return False, f"unknown baseline: {baseline}"
        identity = _current_identity()
        run_dir = _run_dir(model, identity["prompt_sha256"])
        path = run_dir / f"{baseline}.seal.json"
        seal = json.loads(path.read_text())
        expected = {
            "seal_version": SEAL_VERSION,
            "model": model,
            "baseline": baseline,
            **identity,
        }
        for key, value in expected.items():
            if seal.get(key) != value:
                return False, f"{path}: mismatched {key}"
        provenance = (seal.get("git_commit"), seal.get("completed_at"))
        if not all(isinstance(value, str) for value in provenance):
            return False, f"{path}: incomplete completion provenance"
        artifacts = seal.get("artifacts")
        if not isinstance(artifacts, dict) or set(artifacts) != set(STEPS[baseline]):
            return False, f"{path}: incomplete artifact checksums"
        for step in STEPS[baseline]:
            artifact = run_dir / f"{step}.json"
            if artifacts[step] != _sha256(artifact):
                return False, f"{path}: changed {step}.json"
        return True, str(path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return False, str(error)


def evaluation_parser_identity() -> dict:
    """Return the frozen parser configuration recorded by evaluation seals."""
    prompt = ROOT / "baselines" / "baseline_prompts" / EVALUATION_PARSER_PROMPT
    return {
        "model": EVALUATION_PARSER_MODEL,
        "profile": EVALUATION_PARSER_PROFILE,
        "prompt": EVALUATION_PARSER_PROMPT,
        "prompt_sha256": _sha256(prompt),
        "max_attempts": EVALUATION_PARSER_MAX_ATTEMPTS,
    }


def validate_evaluation_seal(model: str, baseline: str) -> tuple[bool, str]:
    """Validate an evaluation seal against its raw seal and output bytes."""
    try:
        valid, reason = validate_seal(model, baseline)
        if not valid:
            return False, f"invalid raw seal: {reason}"
        identity = _current_identity()
        raw_dir = _run_dir(model, identity["prompt_sha256"])
        output_dir = ROOT / "results" / "evaluation" / model / baseline
        path = output_dir / "evaluation.seal.json"
        seal = json.loads(path.read_text())
        if seal.get("seal_version") != EVALUATION_SEAL_VERSION:
            return False, f"{path}: mismatched seal_version"
        if seal.get("model") != model or seal.get("baseline") != baseline:
            return False, f"{path}: mismatched run identity"
        if seal.get("evaluator") != {
            "id": EVALUATOR_ID,
            "version": EVALUATOR_VERSION,
        }:
            return False, f"{path}: mismatched evaluator identity"
        raw_seal = raw_dir / f"{baseline}.seal.json"
        if seal.get("raw_seal_sha256") != _sha256(raw_seal):
            return False, f"{path}: changed raw seal"
        if seal.get("parser") != evaluation_parser_identity():
            return False, f"{path}: mismatched parser configuration"
        artifacts = seal.get("artifacts")
        expected = {
            "direct_json_parse.json" if baseline == "direct" else "sql_json_parse.json",
            "geocodes.json",
            "per_question.jsonl",
        }
        if not isinstance(artifacts, dict) or set(artifacts) != expected:
            return False, f"{path}: incomplete artifact checksums"
        for name in expected:
            if artifacts[name] != _sha256(output_dir / name):
                return False, f"{path}: changed {name}"
        return True, str(path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return False, str(error)
