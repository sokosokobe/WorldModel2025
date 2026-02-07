#!/bin/bash
# source start_vwa.sh

# 1. Dockerコンテナの起動
echo "Starting Docker container..."
docker start shopping

# 2. Conda環境の有効化
# 注意: スクリプト内でconda activateするために必要な記述
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate vwa

# 3. 環境変数の設定
# .envファイルがあれば読み込む
if [ -f .env ]; then
    export $(cat .env | xargs)
fi
export DATASET=visualwebarena
export PLAYWRIGHT_DEFAULT_TIMEOUT=60000

# サーバーURL設定
export SHOPPING="http://localhost:7770"
export SHOPPING_ADMIN="http://localhost:7780/admin"
export REDDIT="http://localhost:9999"
export WIKIPEDIA="http://localhost:8888"
export HOMEPAGE="http://localhost:4399"
export CLASSIFIEDS="http://localhost:9980"
export CLASSIFIEDS_RESET_TOKEN="dummy_token"

# 4. 前回の結果ファイルの削除
echo "Cleaning up previous results..."
rm -rf result_shopping_test
rm -rf result_shopping_gemini

echo "Setup complete! Environment 'vwa' is active."