#!/bin/bash
# chmod +x eval/classifieds/run_test.sh
#
# Prerequisites:
# - source .venv/bin/activate
# - export OPENAI_API_KEY=...
# - export DATASET=visualwebarena
# - export CLASSIFIEDS=http://<host>:9980/
# - export CLASSIFIEDS_RESET_TOKEN=...
#
# Example:
#   set -a; source .env; set +a
#   export PLAYWRIGHT_DEFAULT_TIMEOUT=120000
#   eval/classifieds/run_test.sh

set -euo pipefail

INSTRUCTION_PATH="${INSTRUCTION_PATH:-agent/prompts/jsons/p_som_cot_id_actree_3s.json}"
PICKUP_JSON="${PICKUP_JSON:-config_files/vwa/test_classifieds.pickup_fast.json}"
RESULT_DIR="${RESULT_DIR:-result_classifieds_eval}"
CONFIG_DIR="${CONFIG_DIR:-${RESULT_DIR}/_configs}"
MODEL="${MODEL:-gpt-4o}"
MAX_STEPS="${MAX_STEPS:-30}"
ACTION_SET_TAG="${ACTION_SET_TAG:-som}"
OBSERVATION_TYPE="${OBSERVATION_TYPE:-image_som}"
RENDER="${RENDER:-1}" # 1: enable --render, 0: disable

rm -rf "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"

echo "Materializing pickup json into numbered configs..."
./.venv/bin/python scripts/materialize_test_dir.py \
  --input_json "${PICKUP_JSON}" \
  --output_dir "${CONFIG_DIR}" \
  --skip_login

N="$(
  find "${CONFIG_DIR}" -maxdepth 1 -name '*.json' \
    -exec basename {} .json \; \
    | awk '$1 ~ /^[0-9]+$/' \
    | wc -l \
    | tr -d ' '
)"

echo "Running classifieds eval: N=${N}"
echo "  PICKUP_JSON=${PICKUP_JSON}"
echo "  CONFIG_DIR=${CONFIG_DIR}"
echo "  RESULT_DIR=${RESULT_DIR}"

render_flag=()
if [[ "${RENDER}" == "1" ]]; then
  render_flag+=(--render)
fi

for i in $(seq 0 $((N-1))); do
  echo "==> Task ${i}/${N}"
  ./.venv/bin/python run.py \
    --instruction_path "${INSTRUCTION_PATH}" \
    --test_config_base_dir "${CONFIG_DIR}" \
    --result_dir "${RESULT_DIR}/${i}" \
    --test_start_idx "${i}" \
    --test_end_idx "$((i+1))" \
    --max_steps "${MAX_STEPS}" \
    --model "${MODEL}" \
    --action_set_tag "${ACTION_SET_TAG}" \
    --observation_type "${OBSERVATION_TYPE}" \
    "${render_flag[@]}"
done

echo
echo "==> Summary"
python evaluate_results.py --result_dir "${RESULT_DIR}" --recursive
