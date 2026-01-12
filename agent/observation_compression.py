import json
import os
import re
from typing import Any


DEFAULT_WEIGHTS: dict[str, Any] = {
    "token_overlap_weight": 1.0,
    "tag_bonus": {
        "INPUT": 0.3,
        "TEXTAREA": 0.3,
        "SELECT": 0.2,
        "BUTTON": 0.2,
        "A": 0.1,
        "StaticText": 0.0,
    },
}


def load_weights(path: str | None) -> dict[str, Any]:
    if not path:
        return DEFAULT_WEIGHTS
    if not os.path.exists(path):
        return DEFAULT_WEIGHTS
    with open(path, "r") as f:
        data = json.load(f)
    merged = dict(DEFAULT_WEIGHTS)
    merged.update(data or {})
    return merged


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_line(line: str, objective: str, weights: dict[str, Any]) -> float:
    tokens = _tokenize(objective)
    lower = line.lower()
    overlap = sum(1 for t in tokens if t in lower)
    score = overlap * float(weights.get("token_overlap_weight", 1.0))
    match = re.match(r"^\\[(.*?)\\]\\s+\\[(.*?)\\]\\s+\\[(.*)\\]", line)
    if match:
        tag = match.group(2)
        score += float(weights.get("tag_bonus", {}).get(tag, 0.0))
    return score


def select_lines(
    obs: str,
    objective: str,
    limit: int,
    weights: dict[str, Any],
) -> tuple[str, list[str]]:
    if limit <= 0:
        return obs, []
    lines = obs.splitlines()
    prefix: list[str] = []
    content_lines: list[str] = []
    in_content = False
    for line in lines:
        if line.startswith("["):
            in_content = True
        if in_content:
            content_lines.append(line)
        else:
            prefix.append(line)

    if len(content_lines) <= limit:
        return obs, content_lines

    scored = [(score_line(line, objective, weights), line) for line in content_lines]
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    top_lines = [line for _, line in scored[:limit]]
    return "\n".join(prefix + top_lines), top_lines


def log_compression_example(
    path: str,
    objective: str,
    observation: str,
    selected_lines: list[str],
) -> None:
    record = {
        "objective": objective,
        "observation": observation,
        "selected_lines": selected_lines,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")
