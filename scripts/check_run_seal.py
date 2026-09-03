#!/usr/bin/env python3
"""Return success when one official baseline run has a valid seal."""

import sys

from vigsqa.sealing import validate_seal


def main() -> int:
    try:
        _, model, baseline = sys.argv
    except ValueError:
        print(f"usage: {sys.argv[0]} MODEL BASELINE", file=sys.stderr)
        return 2
    valid, reason = validate_seal(model, baseline)
    status = "sealed" if valid else "incomplete"
    print(f"[INFO] {model} — {baseline}: {status} ({reason})")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
