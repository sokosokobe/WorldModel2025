# python evaluate_results.py

import os
import glob
import re

# 結果フォルダのパス
result_dir = "result_test"
log_list_file = os.path.join(result_dir, "log_files.txt")

print(f"📊 Evaluating results in: {result_dir}")

if not os.path.exists(log_list_file):
    print(f"⚠️ {log_list_file} not found.")
    exit(1)

with open(log_list_file, "r") as f:
    log_files = [line.strip() for line in f if line.strip()]

total = 0
success = 0
results = []

print("-" * 70)
print(f"{'Task ID':<10} | {'Score':<10} | {'Result'}")
print("-" * 70)

# ログファイルから結果を抽出
for log_path in log_files:
    if not os.path.exists(log_path):
        print(f"Warning: Log file {log_path} not found.")
        continue

    with open(log_path, "r") as f:
        content = f.read()

    # 1つのログファイルに複数タスクの結果が含まれている場合に対応
    # [Config file] と [Result] のペアを抽出
    config_matches = re.findall(r"\[Config file\]: .*/(\d+)\.json", content)
    result_matches = re.findall(r"\[Result\] \((PASS|FAIL)\)", content)

    # ペアが一致していれば、各タスクの結果を記録
    if len(config_matches) == len(result_matches):
        for task_id, result in zip(config_matches, result_matches):
            if result == "PASS":
                score = 1.0
                pass_fail = "✅ PASS"
                success += 1
            else:
                score = 0.0
                pass_fail = "❌ FAIL"
            total += 1
            results.append((task_id, score, pass_fail))
    else:
        # フォールバック: 従来の方法で処理
        task_id = "Unknown"
        score = 0.0
        pass_fail = "❌ FAIL"

        config_match = re.search(r"\[Config file\]: .*/(\d+)\.json", content)
        if config_match:
            task_id = config_match.group(1)

        if "[Result] (PASS)" in content:
            score = 1.0
            pass_fail = "✅ PASS"
            success += 1
        elif "[Result] (FAIL)" in content:
            score = 0.0
            pass_fail = "❌ FAIL"

        total += 1
        results.append((task_id, score, pass_fail))

# ID順にソートして表示
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
