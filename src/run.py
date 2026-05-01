"""CLI entrypoint.

Usage:
    python -m src.run --prompt "design a 2 km bridge for 50 cars/h"
    python -m src.run --replay <run_id>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from src.orchestrator import replay, run_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", help="user design prompt")
    p.add_argument("--replay", help="run_id to replay (no LLM calls)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.replay:
        out = replay(args.replay)
    elif args.prompt:
        out = run_pipeline(args.prompt)
    else:
        p.error("--prompt or --replay required")
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
