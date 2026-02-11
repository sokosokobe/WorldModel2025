#!/bin/bash
# chmod +x run_easy_tasks_gpt5_2.sh
# ./run_easy_tasks_gpt5_2.sh

# ==========================================
# Easyタスク一括実行スクリプト
# ==========================================

# 1. 実行したいタスクIDのリスト (スペース区切りで記述)
#    先ほど見つかったIDをすべて入れます
TASK_IDS="8 13 14 15 16 17 24 25 26 27 28 29 36 37 38"

# 2. 設定
#    APIキーは事前にexportしておくか、ここに直接書いてもOK
#    export GEMINI_API_KEY="your_key"
#    export OPENAI_API_KEY="your_key"

# モデル設定 (コメントアウトを切り替えて使用)
# --- GPT-5.2用 ---
MODEL="gpt-5.2"
PROVIDER="openai"
RESULT_DIR="result_shopping_gpt5_2"
export DATASET="visualwebarena"

# --- GPT-4o用 ---
# MODEL="gpt-4o"
# PROVIDER="openai"
# RESULT_DIR="result_shopping_gpt4o_easy"

# 3. 実行ループ
echo "🚀 Starting Batch Execution for Tasks: $TASK_IDS"
echo "Model: $MODEL, Provider: $PROVIDER"
echo "Results will be saved to: $RESULT_DIR"

# フォルダを初期化 (過去の結果を消したい場合)
# rm -rf $RESULT_DIR

for ID in $TASK_IDS; do
    NEXT_ID=$((ID + 1))
    echo "--------------------------------------------------"
    echo "▶️ Running Task ID: $ID"
    echo "--------------------------------------------------"
    
    /Users/sokosokobe/miniforge3/envs/vwa/bin/python run.py \
      --instruction_path agent/prompts/jsons/p_som_cot_id_actree_3s.json \
      --test_start_idx $ID \
      --test_end_idx $NEXT_ID \
      --result_dir $RESULT_DIR \
      --test_config_base_dir config_files/vwa/test_shopping \
      --model $MODEL \
      --provider $PROVIDER \
      --action_set_tag som \
      --observation_type image_som \
      --render

    # サーバーへの負荷軽減のため少し待機
    sleep 2
done

echo "✅ All tasks completed!"
