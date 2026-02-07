#!/bin/bash
# chmod +x run_test.sh
# ./run_test.sh

python run.py \
  --instruction_path agent/prompts/jsons/p_som_cot_id_actree_3s.json \
  --test_start_idx 0 \
  --test_end_idx 999999 \
  --result_dir result_test \
  --test_config_base_dir config_files/vwa/test \
  --model gpt-4o \
  --action_set_tag som \
  --observation_type image_som \
  --render