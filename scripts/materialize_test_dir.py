#!/usr/bin/env python3

"""
Materialize a VWA task list JSON (array of configs) into a run.py-compatible
directory containing numbered `0.json`, `1.json`, ... files.

Typical usage (from repo root):

  ./.venv/bin/python scripts/materialize_test_dir.py \
    --input_json config_files/vwa/test_classifieds.pickup_fast.json \
    --output_dir /tmp/test_classifieds_pickup

This script also resolves placeholder URLs like `__CLASSIFIEDS__` using the
current environment variables (`CLASSIFIEDS`, `SHOPPING`, `REDDIT`, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


PLACEHOLDER_TO_ENV = {
    "__CLASSIFIEDS__": "CLASSIFIEDS",
    "__SHOPPING__": "SHOPPING",
    "__REDDIT__": "REDDIT",
    "__WIKIPEDIA__": "WIKIPEDIA",
    "__HOMEPAGE__": "HOMEPAGE",
    "__SHOPPING_ADMIN__": "SHOPPING_ADMIN",
}


def _normalize_base_url(url: str) -> str:
    # Keep scheme+host+port; strip trailing slashes for safe concatenation.
    return url.rstrip("/")


def _resolve_placeholders(value: str) -> str:
    out = value
    for placeholder, env_name in PLACEHOLDER_TO_ENV.items():
        env_val = os.environ.get(env_name)
        if not env_val:
            continue
        out = out.replace(placeholder, _normalize_base_url(env_val))
    return out


def _walk_and_replace(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _walk_and_replace(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_and_replace(v) for v in obj]
    if isinstance(obj, str):
        return _resolve_placeholders(obj)
    return obj


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_json", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument(
        "--skip_login",
        action="store_true",
        help="Force require_login=false and storage_state=null for all tasks.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_json)
    output_dir = Path(args.output_dir)

    tasks = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise SystemExit("input_json must be a JSON array of task configs.")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Also write an index file for convenience/debugging.
    (output_dir / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for idx, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise SystemExit(f"Task {idx} is not an object.")

        materialized = _walk_and_replace(task)
        if args.skip_login:
            materialized["require_login"] = False
            materialized["storage_state"] = None

        (output_dir / f"{idx}.json").write_text(
            json.dumps(materialized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"Wrote {len(tasks)} task configs to: {output_dir}")


if __name__ == "__main__":
    main()

