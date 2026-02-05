# VWA タスクピックアップ（冗長タスクの削ぎ落とし）レポート

目的：`feat/*` / `integrate/*` ブランチの成功率比較を短時間で回すために、`config_files/vwa/*raw.json` から **冗長なタスク（同一タイプ/類似intent）を削ぎ落とした小集合**を作る。

このレポートでは、Classifieds / Reddit / Shopping それぞれについて、
- **Stage 1（機械的削ぎ落とし）**：`intent_template_id` を軸に「同じタイプ」を代表1件にして縮約
- **Stage 2（見比べて削ぎ落とし）**：類似intentの多い型・マルチサイト・reset重いタスクを落としてさらに小さく

…という2段階の方針と、何を落として何を残したかをまとめる。

---

## 共通：Stage 1（機械的削ぎ落とし）

- 方針：`intent_template_id` ごとにグループ化し、各テンプレートから代表を最大1件だけ採用（=「同じタイプの大量バリエーション」を落とす）
- 追加の多様性確保：intentのキーワード特徴でタイプ推定し、`budget` 以内で偏りを抑えて抽出
- 近似重複の抑制：intentをトークン化し、Jaccard類似度が高すぎるものは除外

生成ファイル（Stage 1）
- Classifieds: `test_classifieds.pickup.json`（24件）
- Reddit: `test_reddit.pickup.json`（24件）
- Shopping: `test_shopping.pickup.json`（24件）

---

## Classifieds

### 元データ
- `test_classifieds.raw.json`: 234件（うち multi-site 15件 / require_reset 22件）

### Stage 1（機械的）
- `test_classifieds.pickup.json`: 24件
- 削ぎ落としたもの：
  - 同一テンプレ（`intent_template_id`）の多数バリエーション

### Stage 2（見比べて削ぎ落とし）
- `test_classifieds.pickup_fast.json`: 12件（高速スクリーニング用）
- `test_classifieds.pickup_interactive.json`: 4件（投稿/コメント等の操作系を分離）
- 見比べて落とした主なポイント：
  - **multi-site start_url（`|AND|`）** を含むタスク（Reddit/Shopping参照が入ると検証対象が増えて時間が伸びる）
  - **require_reset=true** のタスクは fast から外し、interactive 側に分離
- 残したもの（fastの狙い）：
  - 検索・カテゴリ移動・比較（最安/色/条件）・詳細抽出など、失敗モードが分かれる型を優先

---

## Reddit

### 元データ
- `test_reddit.raw.json`: 210件（うち multi-site 40件 / require_reset 21件）

### Stage 1（機械的）
- `test_reddit.pickup.json`: 24件
- 削ぎ落としたもの：
  - 同一テンプレ（`intent_template_id`）の多数バリエーション

### Stage 2（見比べて削ぎ落とし）
- `test_reddit.pickup_fast.json`: 12件（単一サイト + reset除外）
- さらに類似を見比べて圧縮した集合：
  - `test_reddit.pickup_pruned.json`: 9件
- 見比べて落とした主なポイント：
  - **「画像内の物体数を数えてコメント」型が複数（例：鍵盤/木星/kirby）** → 代表1件に集約
    - 残した理由：画像理解＋コメント投稿＋フォーマット遵守が同時に評価でき、難易度が比較的高い
  - 同じ“コメント投稿”でも内容が異なる（紙幣額+国名、DataIsBeautifulの数値抽出など）は残して多様性確保
- 残したもの（prunedの狙い）：
  - コメント系（画像数え上げ/紙幣）
  - interaction系（repost/特定条件の投稿探索/URL抽出）
  - reading系（数値や旗色の抽出）
  - search系（写真から都市subreddit探索）

---

## Shopping

### 元データ
- `test_shopping.raw.json`: 466件（うち multi-site 7件 / require_reset 19件）

### Stage 1（機械的）
- `test_shopping.pickup.json`: 24件
- 削ぎ落としたもの：
  - 同一テンプレ（`intent_template_id`）の多数バリエーション

### Stage 2（見比べて削ぎ落とし）
- `test_shopping.pickup_fast.json`: 12件（単一サイト + reset除外）
- さらに類似を見比べて圧縮した集合：
  - `test_shopping.pickup_pruned.json`: 8件
- 見比べて落とした主なポイント：
  - **「buy/order/checkout」型が複数** → 住所入力/数量/レビュー数条件など性質が違うものだけ残し、重複は削除
  - **「色違いを探す」型が複数（服/靴/家具など）** → cart操作が入るもの、wishlist操作が入るもの等、評価観点が異なるものを優先
  - 「最安を探してカート」系は同質になりやすいので代表を残して圧縮
- 残したもの（prunedの狙い）：
  - 検索→一覧→抽出（価格帯/商品名）
  - 色・条件付き比較（wishlist/cart）
  - 画像条件付き探索（複数画像のAND条件）
  - 購入フロー（住所/電話/制約）
  - レビュー投稿

---

## 実行時の使い分け（おすすめ）

- まずは Stage 2（pruned or fast）でスクリーニング：
  - Classifieds: `test_classifieds.pickup_fast.json`（12）
  - Reddit: `test_reddit.pickup_pruned.json`（9）
  - Shopping: `test_shopping.pickup_pruned.json`（8）
- 成果が出たブランチだけ Stage 1（pickup.json 24件）に拡張して本評価

---

## 生成スクリプト
- `scripts/pickup_classifieds_tasks.py`（Classifieds専用）
- `scripts/pickup_vwa_tasks.py`（汎用：reddit/shopping含む）

