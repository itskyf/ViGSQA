#!/usr/bin/env python3
"""Parse and score one raw-sealed ViGSQA v3 baseline."""

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pyproj import Geod
from shapely import from_wkt
from tqdm import tqdm

from baselines import pipeline
from baselines.baselines_vi import (
    INFERENCE_PROFILE,
    build_model_vi,
    setup_llm_cache,
)
from vigsqa.sealing import (
    EVALUATION_PARSER_MAX_ATTEMPTS,
    EVALUATION_PARSER_MODEL,
    EVALUATION_PARSER_PROFILE,
    EVALUATION_PARSER_PROMPT,
    EVALUATION_SEAL_VERSION,
    EVALUATOR_ID,
    EVALUATOR_VERSION,
    evaluation_parser_identity,
    validate_seal,
)

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PER_TID = 100
RAW_STEPS = {"direct": "direct_answer", "text2sql": "sql_answer"}
PARSE_FILES = {"direct": "direct_json_parse.json", "text2sql": "sql_json_parse.json"}
PARSER_PROMPT_PATH = ROOT / "baselines" / "baseline_prompts" / EVALUATION_PARSER_PROMPT
if INFERENCE_PROFILE != EVALUATION_PARSER_PROFILE:
    raise RuntimeError(
        "parser decoding profile differs from the frozen evaluation seal"
    )
TID_FAMILIES = {
    "T01": "entity",
    "T02": "entity",
    "T03": "entity",
    "T04": "entity",
    "T05": "entity",
    "T06": "entity",
    "T07": "textual_fact",
    "T08": "entity",
    "T09": "entity",
    "T10": "entity",
    "T11": "entity",
    "T12": "entity",
    "T13": "location",
    "T14": "location",
    "T15": "location",
    "T16": "location",
    "T17": "location",
    "T18": "location",
    "T19": "location",
    "T20": "location",
    "T21": "direction",
    "T22": "direction",
    "T23": "count",
    "T24": "count",
    "T25": "distance",
    "T26": "distance",
    "T27": "area",
    "T28": "length",
}
SECTORS = (
    "bắc",
    "đông bắc",
    "đông",
    "đông nam",
    "nam",
    "tây nam",
    "tây",
    "tây bắc",
)
NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][-+]?\d+)?")


def sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def normalize_text(value: object) -> str:
    """Normalize text without removing Vietnamese diacritics or numbers."""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = "".join(
        " " if unicodedata.category(char).startswith("P") else char for char in text
    )
    return " ".join(text.split())


def text_score(prediction: str, gold: str) -> dict:
    predicted = normalize_text(prediction).split()
    expected = normalize_text(gold).split()
    if not predicted:
        return {"attempted": False, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    precision = overlap / len(predicted)
    recall = overlap / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"attempted": True, "precision": precision, "recall": recall, "f1": f1}


def sector(angle: float) -> str:
    return SECTORS[int(((angle % 360) + 22.5) // 45) % 8]


def finite_number(value: object, family: str) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number, unit = float(value), ""
    elif isinstance(value, str):
        match = NUMBER_RE.search(value)
        if not match:
            return None
        token = match.group().replace(",", ".")
        try:
            number = float(token)
        except ValueError:
            return None
        unit = normalize_text(value[match.end() :]).replace("²", "2")
    else:
        return None
    if not math.isfinite(number):
        return None
    if family in ("distance", "length"):
        if unit in ("km", "kilômét", "kilomet", "kilometer"):
            number *= 1000
        elif unit in ("cm", "centimét", "centimet"):
            number /= 100
        elif unit not in ("", "m", "mét", "met", "meter"):
            return None
    elif family == "area":
        if unit in ("km2", "km^2", "kilômét vuông", "kilomet vuông"):
            number *= 1_000_000
        elif unit in ("ha", "hecta", "hectare"):
            number *= 10_000
        elif unit not in ("", "m2", "m^2", "mét vuông", "met vuông"):
            return None
    elif family == "count" and not number.is_integer():
        return None
    return number


def nested_values(data: object, keys: set[str]) -> list[object]:
    values = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys:
                values.extend(value if isinstance(value, list) else [value])
            elif isinstance(value, (dict, list)):
                values.extend(nested_values(value, keys))
    elif isinstance(data, list):
        for value in data:
            values.extend(nested_values(value, keys))
    return values


def json_block_error(content, finish_reason):
    """Require a fenced JSON value accepted by the scoring parser."""
    if isinstance(content, str) and pipeline.extract_json_blocks(content):
        return None
    return "invalid_json_output: no parseable JSON block"


def candidates(question: dict, parsed: list[object], family: str) -> list:
    if family == "entity":
        values = nested_values(parsed, {"name"})
    elif family == "textual_fact":
        values = nested_values(
            parsed, {question["answers"][0]["multi_source_attribute"]}
        )
    elif family == "location":
        values = nested_values(parsed, {"address"})
    elif family == "direction":
        values = nested_values(parsed, {"azimuth_angle", "angle"})
    else:
        values = nested_values(parsed, {family})

    result = []
    for value in values:
        if family in ("entity", "textual_fact", "location"):
            if isinstance(value, str) and value.strip():
                result.append(value.strip())
        else:
            number = finite_number(value, family)
            if number is not None:
                result.append(number % 360 if family == "direction" else number)
    return result


def gold_values(question: dict, family: str) -> list:
    keys = {
        "entity": ("poi_name", "park_name", "road_name"),
        "textual_fact": ("multi_source_answer",),
        "location": ("address",),
        "direction": ("angle",),
        "count": ("count",),
        "distance": ("distance",),
        "area": ("area",),
        "length": ("length",),
    }[family]
    return [
        answer[key] for answer in question["answers"] for key in keys if key in answer
    ]


def best_text(predictions: list, golds: list) -> tuple[dict, int | None, int | None]:
    if not predictions:
        return text_score("", golds[0] if golds else ""), None, None
    scored = [
        (text_score(pred, gold), pi, gi)
        for pi, pred in enumerate(predictions)
        for gi, gold in enumerate(golds)
    ]
    return max(scored, key=lambda item: (item[0]["f1"], -item[1], -item[2]))


def best_error(
    predictions: list[float], golds: list[float], family: str
) -> tuple[dict, int | None, int | None]:
    if not predictions:
        return {"attempted": False, "error": 1.0}, None, None
    scored = []
    for pi, prediction in enumerate(predictions):
        for gi, gold in enumerate(golds):
            if family == "direction":
                error = abs((prediction - gold + 180) % 360 - 180) / 180
            else:
                error = (
                    0.0
                    if gold == prediction
                    else min(abs(prediction - gold) / abs(gold), 1.0)
                    if gold
                    else 1.0
                )
            scored.append(({"attempted": True, "error": error}, pi, gi))
    return min(scored, key=lambda item: (item[0]["error"], item[1], item[2]))


def validate_questions(questions: list[dict]) -> None:
    manifest = json.loads((pipeline.QUESTIONS_DIR / "MANIFEST.json").read_text())
    mapping = manifest.get("tid_to_type")
    if not isinstance(mapping, dict) or set(mapping) != set(TID_FAMILIES):
        raise ValueError("manifest TIDs are missing or unknown")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("manifest contains duplicate TID type assignments")
    ids = [question.get("id") for question in questions]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("questions contain missing or duplicate QIDs")
    seen = Counter(question.get("tid") for question in questions)
    if set(seen) != set(TID_FAMILIES) or any(
        count != EXPECTED_PER_TID for count in seen.values()
    ):
        raise ValueError(f"question TIDs are missing, unknown, or duplicated: {seen}")
    mismatches = [
        question["id"]
        for question in questions
        if mapping.get(question["tid"]) != question["type"]
    ]
    if mismatches:
        raise ValueError(f"question TIDs mismatch the manifest: {mismatches[:20]}")


def parse_answers(
    questions: list[dict],
    answers: list[dict],
    model,
    output: Path,
    concurrency: int,
) -> list[dict]:
    existing = json.loads(output.read_text()) if output.exists() else []
    existing_ids = [record.get("id") for record in existing]
    question_ids = {question["id"] for question in questions}
    if (
        len(existing_ids) != len(set(existing_ids))
        or not set(existing_ids) <= question_ids
    ):
        raise ValueError(f"{output}: duplicate or unknown parse IDs")
    cached = {record["id"]: record for record in existing}
    frozen = set(existing_ids) == question_ids
    prompt = PARSER_PROMPT_PATH.read_text()
    todo = []
    for question, answer in zip(questions, answers, strict=True):
        if question["id"] in cached and (
            frozen or not cached[question["id"]].get("error")
        ):
            continue
        active_prompt = prompt
        if question["tid"] == "T07":
            key = question["answers"][0]["multi_source_attribute"]
            active_prompt = prompt.replace("%OTHER_ATT%", f'"{key}": string')
        else:
            active_prompt = prompt.replace("%OTHER_ATT%", "")
        answer_text = answer.get("content", "")
        todo.append(
            (
                question,
                [
                    SystemMessage(content=active_prompt),
                    HumanMessage(
                        content=(
                            f"Question: {question['question']}\nAnswer: {answer_text}"
                        )
                    ),
                ],
            )
        )
    if todo:
        calls = [messages for _, messages in todo]
        completions = pipeline.invoke_or_capture_many(
            model,
            calls,
            concurrency,
            pipeline.StageValidation(json_block_error, EVALUATION_PARSER_MAX_ATTEMPTS),
        )
        with tqdm(total=len(todo), desc="  parse_answers") as progress:
            for (question, _), (content, error, gen) in zip(
                todo, completions, strict=True
            ):
                cached[question["id"]] = {
                    "id": question["id"],
                    "content": content,
                    **({"error": error} if error else {}),
                    **({"gen": gen} if gen else {}),
                }
                output.write_text(
                    json.dumps(
                        [cached[q["id"]] for q in questions if q["id"] in cached],
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                progress.update(1)
    return [cached[question["id"]] for question in questions]


def load_geocodes(path: Path, addresses: list[str], geocoder) -> list[dict]:
    records = json.loads(path.read_text()) if path.exists() else []
    by_address = {record["address"]: record for record in records}
    missing = [address for address in addresses if address not in by_address]
    for address in tqdm(missing, desc="  geocode_addresses"):
        try:
            location = geocoder.geocode(address, exactly_one=True)
        except GeocoderServiceError as error:
            raise RuntimeError(
                f"transient Nominatim failure for {address!r}: {error}"
            ) from error
        record = {"address": address, "status": "found" if location else "not_found"}
        if location:
            record.update(
                latitude=float(location.latitude), longitude=float(location.longitude)
            )
        by_address[address] = record
        path.write_text(
            json.dumps(
                [by_address[item] for item in addresses if item in by_address],
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    ordered = [by_address[address] for address in addresses]
    path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")
    return ordered


def evaluate(
    questions: list[dict], parsed_records: list[dict], geocodes: list[dict]
) -> list[dict]:
    geocode_by_address = {record["address"]: record for record in geocodes}
    geod = Geod(ellps="WGS84")
    rows = []
    for question, parse_record in zip(questions, parsed_records, strict=True):
        family = TID_FAMILIES[question["tid"]]
        parsed = pipeline.extract_json_blocks(parse_record.get("content", ""))
        predicted = candidates(question, parsed, family)
        golds = gold_values(question, family)
        metrics = {}
        selected = {}
        if family in ("entity", "textual_fact", "location"):
            score, pi, gi = best_text(predicted, golds)
            metrics["text"] = score
            selected["text"] = {"prediction": pi, "gold": gi}
        if family == "location":
            spatial = []
            for pi, address in enumerate(predicted):
                geocode = geocode_by_address[address]
                if geocode["status"] != "found":
                    continue
                for gi, answer in enumerate(question["answers"]):
                    point = from_wkt(answer["geo_wkt"]).centroid
                    distance = geod.inv(
                        geocode["longitude"], geocode["latitude"], point.x, point.y
                    )[2]
                    spatial.append(
                        (
                            {"attempted": True, "error": min(distance / 500_000, 1.0)},
                            pi,
                            gi,
                        )
                    )
            if spatial:
                score, pi, gi = min(
                    spatial, key=lambda item: (item[0]["error"], item[1], item[2])
                )
            else:
                score, pi, gi = {"attempted": False, "error": 1.0}, None, None
            metrics["spatial"] = score
            selected["spatial"] = {"prediction": pi, "gold": gi}
        elif family == "direction":
            text_predictions = [sector(value) for value in predicted]
            text_golds = [sector(float(value)) for value in golds]
            score, pi, gi = best_text(text_predictions, text_golds)
            metrics["text"] = score
            selected["text"] = {"prediction": pi, "gold": gi}
            score, pi, gi = best_error(
                predicted, [float(value) for value in golds], family
            )
            metrics["angle"] = score
            selected["angle"] = {"prediction": pi, "gold": gi}
        elif family in ("count", "distance", "area", "length"):
            score, pi, gi = best_error(
                predicted, [float(value) for value in golds], family
            )
            metrics["relative"] = score
            selected["relative"] = {"prediction": pi, "gold": gi}
        rows.append(
            {
                "id": question["id"],
                "tid": question["tid"],
                "type": question["type"],
                "family": family,
                "candidates": predicted,
                "metrics": metrics,
                "selected": selected,
            }
        )
    return sorted(rows, key=lambda row: row["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--baseline", required=True, choices=("direct", "text2sql"))
    parser.add_argument("--llm-concurrency", required=True, type=int)
    args = parser.parse_args()
    if args.llm_concurrency < 1:
        parser.error("--llm-concurrency must be at least 1")
    valid, reason = validate_seal(args.model, args.baseline)
    if not valid:
        parser.error(f"raw seal is invalid: {reason}")

    questions = pipeline.load_questions("full")
    validate_questions(questions)
    raw_dir = pipeline.CACHE_DIR / args.model
    answers = json.loads((raw_dir / f"{RAW_STEPS[args.baseline]}.json").read_text())
    answers_by_id = {answer["id"]: answer for answer in answers}
    if set(answers_by_id) != {question["id"] for question in questions}:
        parser.error("raw answers do not match frozen question IDs")
    answers = [answers_by_id[question["id"]] for question in questions]

    output_dir = ROOT / "results" / "evaluation" / args.model / args.baseline
    output_dir.mkdir(parents=True, exist_ok=True)
    seal_path = output_dir / "evaluation.seal.json"
    seal_path.unlink(missing_ok=True)
    parse_path = output_dir / PARSE_FILES[args.baseline]
    setup_llm_cache()
    model = build_model_vi(EVALUATION_PARSER_MODEL)
    with ExitStack() as clients:
        if isinstance(model, ChatOpenAI):
            clients.enter_context(model.root_client)
        parsed_records = parse_answers(
            questions,
            answers,
            model,
            parse_path,
            args.llm_concurrency,
        )

    parsed_blocks = [
        pipeline.extract_json_blocks(record.get("content", ""))
        for record in parsed_records
    ]
    address_order = []
    for question, parsed in zip(questions, parsed_blocks, strict=True):
        if TID_FAMILIES[question["tid"]] == "location":
            for address in candidates(question, parsed, "location"):
                if address not in address_order:
                    address_order.append(address)
    geocode_path = output_dir / "geocodes.json"
    geocodes = load_geocodes(
        geocode_path, address_order, Nominatim(user_agent="ViGSQA-v3-evaluator")
    )
    rows = evaluate(questions, parsed_records, geocodes)
    for row in rows:
        row.update(model=args.model, baseline=args.baseline)
    metrics_path = output_dir / "per_question.jsonl"
    metrics_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        )
    )

    raw_seal = raw_dir / f"{args.baseline}.seal.json"
    seal = {
        "seal_version": EVALUATION_SEAL_VERSION,
        "evaluator": {"id": EVALUATOR_ID, "version": EVALUATOR_VERSION},
        "model": args.model,
        "baseline": args.baseline,
        "raw_seal_sha256": sha256(raw_seal),
        "parser": evaluation_parser_identity(),
        "artifacts": {
            parse_path.name: sha256(parse_path),
            geocode_path.name: sha256(geocode_path),
            metrics_path.name: sha256(metrics_path),
        },
    }
    seal_part = seal_path.with_suffix(seal_path.suffix + ".part")
    seal_part.write_text(
        json.dumps(seal, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    seal_part.replace(seal_path)
    print(f"Evaluated {len(rows)} questions; seal: {seal_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
