#!/usr/bin/env python3
"""Pick a diverse subset of VWA Classifieds tasks.

Motivation:
  - `config_files/vwa/test_classifieds.raw.json` contains many tasks that share the same
    `intent_template_id` (i.e., the same "type" with different instantiations).
  - Running *all* tasks across many branches is expensive. This script selects a
    representative and diverse subset for quick screening.

Design:
  1) Group tasks by `intent_template_id` and select up to `--per-template` items per group.
     (Default: 1 per template)
  2) Optionally cap total tasks by `--budget` using type-stratified selection.
  3) Optionally de-duplicate near-identical intents via Jaccard similarity.

Output:
  - JSON list compatible with run.py (`--test_config_base_dir` expects config files there)
  - Optional markdown summary (task_id + intent) for reporting.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_INPUT = "config_files/vwa/test_classifieds.raw.json"


COLOR_WORDS = {
    "red",
    "blue",
    "green",
    "yellow",
    "orange",
    "purple",
    "pink",
    "black",
    "white",
    "gray",
    "grey",
    "brown",
    "beige",
    "silver",
    "gold",
}

STOPWORDS = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "on",
    "in",
    "this",
    "that",
    "with",
    "for",
    "me",
    "my",
    "please",
    "from",
    "and",
    "or",
    "is",
    "are",
    "be",
    "find",
    "help",
    "navigate",
    "site",
}


def _safe_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def tokenize_intent(intent: str) -> set[str]:
    s = intent.lower()
    s = re.sub(r"\$\\s*\\d+(?:\\.\\d+)?", "<money>", s)
    s = re.sub(r"\\d+(?:\\.\\d+)?", "<num>", s)
    s = re.sub(r"[^a-z0-9_<>\\s]+", " ", s)
    tokens = {t for t in s.split() if t and t not in STOPWORDS}
    # Normalize colors to reduce duplicate patterns.
    normed: set[str] = set()
    for t in tokens:
        if t in COLOR_WORDS:
            normed.add("<color>")
        else:
            normed.add(t)
    return normed


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def infer_type(intent: str) -> str:
    s = intent.lower()
    has_price = any(k in s for k in ("cheapest", "most expensive", "least expensive", "under $", "less than $"))
    has_color = any(c in s for c in COLOR_WORDS) or "dark" in s or "light" in s
    has_contact = any(k in s for k in ("phone", "email", "contact", "message", "call", "text"))
    has_date = any(k in s for k in ("posted", "date", "year", "month", "day"))
    has_location = any(k in s for k in ("city", "county", "zip", "state", "pennsylvania", "borough", "near"))
    has_category = any(k in s for k in ("category", "categories", "section", "filter", "select a category"))

    if has_contact:
        return "contact"
    if has_date:
        return "date"
    if has_category:
        return "category"
    if has_price and has_color:
        return "price+color"
    if has_price:
        return "price"
    if has_color:
        return "color"
    if has_location:
        return "location"
    return "general"


@dataclass(frozen=True)
class TaskView:
    task: dict[str, Any]
    template_id: int | None
    task_id: int | str | None
    intent: str
    overall: float
    reasoning: float
    visual: float
    ttype: str
    tokens: set[str]

    @staticmethod
    def from_task(task: dict[str, Any]) -> "TaskView":
        intent = str(task.get("intent") or "")
        return TaskView(
            task=task,
            template_id=task.get("intent_template_id"),
            task_id=task.get("task_id"),
            intent=intent,
            overall=_safe_float(task.get("overall_difficulty")),
            reasoning=_safe_float(task.get("reasoning_difficulty")),
            visual=_safe_float(task.get("visual_difficulty")),
            ttype=infer_type(intent),
            tokens=tokenize_intent(intent),
        )


def pick_per_template(
    tasks: list[TaskView],
    per_template: int,
    seed: int,
) -> list[TaskView]:
    rng = random.Random(seed)
    groups: dict[int | None, list[TaskView]] = defaultdict(list)
    for t in tasks:
        groups[t.template_id].append(t)

    picked: list[TaskView] = []
    for _tid, items in groups.items():
        # Prefer harder tasks for screening, but shuffle within same scores to avoid bias.
        rng.shuffle(items)
        items.sort(
            key=lambda x: (x.overall, x.reasoning, x.visual, len(x.intent)),
            reverse=True,
        )
        picked.extend(items[: max(1, per_template)])
    return picked


def dedup_by_intent(
    tasks: list[TaskView],
    threshold: float,
) -> list[TaskView]:
    if threshold <= 0:
        return tasks
    kept: list[TaskView] = []
    for t in sorted(tasks, key=lambda x: (x.overall, x.reasoning, x.visual), reverse=True):
        if any(jaccard(t.tokens, k.tokens) >= threshold for k in kept):
            continue
        kept.append(t)
    return kept


def allocate_budget(groups: dict[str, list[TaskView]], budget: int) -> dict[str, int]:
    types = list(groups.keys())
    if budget <= 0:
        return {k: len(v) for k, v in groups.items()}
    if not types:
        return {}
    if budget <= len(types):
        # Keep only the largest groups.
        types.sort(key=lambda k: len(groups[k]), reverse=True)
        return {k: (1 if i < budget else 0) for i, k in enumerate(types)}

    total = sum(len(v) for v in groups.values())
    # proportional + at least 1
    alloc = {k: 1 for k in types}
    remaining = budget - len(types)
    if total <= 0:
        return alloc

    weights = {k: len(groups[k]) / total for k in types}
    # largest remainder method
    remainders: list[tuple[float, str]] = []
    for k in types:
        extra = remaining * weights[k]
        take = int(math.floor(extra))
        alloc[k] += take
        remainders.append((extra - take, k))
    leftover = budget - sum(alloc.values())
    remainders.sort(reverse=True)
    for i in range(leftover):
        alloc[remainders[i % len(remainders)][1]] += 1
    return alloc


def pick_with_budget(
    tasks: list[TaskView],
    budget: int,
    seed: int,
    dedup_threshold: float,
) -> list[TaskView]:
    if budget <= 0 or len(tasks) <= budget:
        return dedup_by_intent(tasks, dedup_threshold)

    rng = random.Random(seed)
    groups: dict[str, list[TaskView]] = defaultdict(list)
    for t in tasks:
        groups[t.ttype].append(t)

    for k in list(groups.keys()):
        rng.shuffle(groups[k])
        groups[k].sort(
            key=lambda x: (x.overall, x.reasoning, x.visual, len(x.intent)),
            reverse=True,
        )

    alloc = allocate_budget(groups, budget)
    selected: list[TaskView] = []
    for k, n in alloc.items():
        if n <= 0:
            continue
        selected.extend(groups[k][:n])

    # If we overshoot due to rounding, trim by difficulty.
    selected.sort(key=lambda x: (x.overall, x.reasoning, x.visual), reverse=True)
    selected = selected[:budget]
    selected = dedup_by_intent(selected, dedup_threshold)

    # If de-dup removed too many, fill from remaining pool.
    if len(selected) < budget:
        remaining = [t for t in tasks if t not in selected]
        remaining.sort(key=lambda x: (x.overall, x.reasoning, x.visual), reverse=True)
        for t in remaining:
            if len(selected) >= budget:
                break
            if dedup_threshold > 0 and any(jaccard(t.tokens, k.tokens) >= dedup_threshold for k in selected):
                continue
            selected.append(t)

    return selected


def write_markdown(tasks: Iterable[TaskView], out_path: Path) -> None:
    lines = [
        "# Picked Classifieds Tasks",
        "",
        "| task_id | intent_template_id | type | overall | reasoning | visual | intent |",
        "|---:|---:|---|---:|---:|---:|---|",
    ]
    for t in tasks:
        lines.append(
            f"| {t.task_id} | {t.template_id} | {t.ttype} | {t.overall:.1f} | {t.reasoning:.1f} | {t.visual:.1f} | {t.intent} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--output", default="config_files/vwa/test_classifieds.pickup.json")
    ap.add_argument("--markdown", default="config_files/vwa/test_classifieds.pickup.md")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--per-template", type=int, default=1)
    ap.add_argument(
        "--budget",
        type=int,
        default=24,
        help="Total tasks to keep (0 = no cap). Recommended: 20-40 for screening.",
    )
    ap.add_argument(
        "--dedup-threshold",
        type=float,
        default=0.85,
        help="Jaccard similarity threshold for intent de-duplication (0 disables).",
    )
    args = ap.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    md = Path(args.markdown) if args.markdown else None

    raw = json.loads(inp.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Expected a JSON list of tasks.")

    views = [TaskView.from_task(t) for t in raw]
    stage1 = pick_per_template(views, per_template=max(1, args.per_template), seed=args.seed)
    stage2 = pick_with_budget(stage1, budget=max(0, args.budget), seed=args.seed, dedup_threshold=max(0.0, args.dedup_threshold))

    # Stable ordering for diffs/logs.
    stage2.sort(key=lambda x: (str(x.ttype), -x.overall, int(x.task_id) if str(x.task_id).isdigit() else 10**9))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([t.task for t in stage2], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if md is not None:
        write_markdown(stage2, md)

    print(f"input={inp} tasks={len(raw)} templates={len({v.template_id for v in views})}")
    print(f"picked={len(stage2)} output={out}")
    if md is not None:
        print(f"markdown={md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

