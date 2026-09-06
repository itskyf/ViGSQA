#!/usr/bin/env python3
"""Return success when one official baseline run has a valid seal."""

import argparse

from vigsqa.sealing import validate_evaluation_seal, validate_seal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("baseline", choices=("direct", "text2sql"))
    parser.add_argument("--evaluation", action="store_true")
    args = parser.parse_args()
    validator = validate_evaluation_seal if args.evaluation else validate_seal
    valid, reason = validator(args.model, args.baseline)
    status = "sealed" if valid else "incomplete"
    kind = "evaluation" if args.evaluation else "raw"
    print(f"[INFO] {args.model} — {args.baseline} {kind}: {status} ({reason})")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
