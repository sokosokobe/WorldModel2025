"""
Usage:
  python evaluate_results.py
  python evaluate_results.py --result_dir result_test
  python evaluate_results.py --result_dir result_classifieds_pickup --recursive
"""

import argparse
import os
import re
from pathlib import Path


def _read_log_list_file(log_list_file: Path) -> list[str]:
    with log_list_file.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _collect_log_list_files(result_dir: Path, recursive: bool) -> list[Path]:
    if not recursive:
        return [result_dir / "log_files.txt"]

    # Per-task results may live under result_dir/{0,1,2,...}/log_files.txt
    return sorted(result_dir.rglob("log_files.txt"))


def _extract_results_from_log_content(content: str) -> list[tuple[str, float, str]]:
    extracted: list[tuple[str, float, str]] = []

    config_matches = re.findall(r"\\[Config file\\]: .*/(\\d+)\\.json", content)
    result_matches = re.findall(r"\\[Result\\] \\((PASS|FAIL)\\)", content)

    if len(config_matches) == len(result_matches) and len(config_matches) > 0:
        for task_id, result in zip(config_matches, result_matches):
            if result == "PASS":
                extracted.append((task_id, 1.0, "✅ PASS"))
            else:
                extracted.append((task_id, 0.0, "❌ FAIL"))
        return extracted

    task_id = "Unknown"
    if m := re.search(r"\\[Config file\\]: .*/(\\d+)\\.json", content):
        task_id = m.group(1)

    if "[Result] (PASS)" in content:
        extracted.append((task_id, 1.0, "✅ PASS"))
    elif "[Result] (FAIL)" in content:
        extracted.append((task_id, 0.0, "❌ FAIL"))
    else:
        extracted.append((task_id, 0.0, "❌ FAIL"))

    return extracted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--result_dir",
        default="result_test",
        help="Result directory created by run.py",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search nested result dirs for log_files.txt (e.g., result_dir/0/...)",
    )
    args = parser.parse_args()

    result_dir = Path(args.result_dir)
    print(f"📊 Evaluating results in: {result_dir}")

    log_list_files = _collect_log_list_files(result_dir, args.recursive)
    if not log_list_files:
        print("⚠️ No log_files.txt found.")
        raise SystemExit(1)

    total = 0
    success = 0
    results: list[tuple[str, float, str]] = []

    for log_list_file in log_list_files:
        if not log_list_file.exists():
            continue

        for log_path in _read_log_list_file(log_list_file):
            if not os.path.exists(log_path):
                print(f"Warning: Log file {log_path} not found.")
                continue

            content = Path(log_path).read_text(encoding="utf-8", errors="replace")
            for task_id, score, pass_fail in _extract_results_from_log_content(
                content
            ):
                total += 1
                success += int(score)
                results.append((task_id, score, pass_fail))

    print("-" * 70)
    print(f"{'Task ID':<10} | {'Score':<10} | {'Result'}")
    print("-" * 70)

    for task_id, score, pass_fail in sorted(
        results, key=lambda x: int(x[0]) if x[0].isdigit() else 999
    ):
        print(f"{str(task_id):<10} | {score:<10.1f} | {pass_fail}")

    print("-" * 70)
    if total > 0:
        rate = (success / total) * 100
        print(f"🏆 Total Tasks: {total}")
        print(f"🎉 Success: {success}")
        print(f"💀 Failed: {total - success}")
        print(f"📈 Success Rate: {rate:.2f}%")
    else:
        print("⚠️ No results found in log files.")


if __name__ == "__main__":
    main()
