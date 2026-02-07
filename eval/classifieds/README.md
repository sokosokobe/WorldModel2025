# Classifieds evaluation

This folder provides a small helper script to run the Classifieds pickup set
sequentially (1 task per process) and summarize PASS/FAIL from logs.

## Prerequisites

- Activate your venv: `source .venv/bin/activate`
- Export required env vars (example uses `.env`):

```bash
set -a; source .env; set +a
export PLAYWRIGHT_DEFAULT_TIMEOUT=120000
```

Required variables:

- `OPENAI_API_KEY`
- `DATASET=visualwebarena`
- `CLASSIFIEDS=http://<host>:9980/`
- `CLASSIFIEDS_RESET_TOKEN` (if your setup supports resets)

## Run

```bash
eval/classifieds/run_test.sh
```

Outputs:

- Per-task results under `result_classifieds_eval/<i>/`
- Numbered configs materialized under `result_classifieds_eval/_configs/`
- Summary printed at the end via `python evaluate_results.py --recursive`
