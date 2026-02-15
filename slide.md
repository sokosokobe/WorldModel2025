---
marp: true
theme: gaia
size: 16:9
paginate: true
backgroundColor: #fff
style: |
  section {
    font-size: 24px;
    padding: 40px;
  }
  h1 {
    font-size: 48px;
    color: #005a9c;
  }
  h2 {
    font-size: 36px;
    color: #005a9c;
    border-bottom: 2px solid #ccc;
    padding-bottom: 10px;
    margin-bottom: 20px;
  }
  table {
    font-size: 20px;
    margin-left: auto;
    margin-right: auto;
    height: 400px;
    width: 800px;
    table-layout: fixed;
  }
  th {
    background-color: #020203;
    color: #fff;
  }
  th:nth-child(1), td:nth-child(1) {
    width: 300px; /* または 30% など */
  }
---

# VWAにおけるWebエージェント<br>実装改良の効果分析

**Effect Analysis of Implementation Improvements for Web Agents in VisualWebArena**

---

## 1. 研究背景

- **Webエージェントの進化**
  - LLMの能力向上により、Webブラウザ操作の自動化が進展
  - 基礎的な操作を行う環境（World of Bits）から、実世界に近いベンチマーク（WebArena, **VisualWebArena (VWA)**）へ

- **現状の課題**
  - 実サイトの観測情報（DOM/画像）は長大
  - LLMのコンテキスト長制約や「迷子」問題
  - **視覚情報と言語指示のグラウンディング（結びつき）の難しさ**

- **先行研究の傾向**
  - モデル中心のアプローチ（WebGUM, WebAgent）が主流
  - **「既存モデル（GPT-4等）の実装・プロンプト工夫」による効果分析は不足**

---

## 2. 研究目的

VisualWebArena (VWA) を評価基盤とし、**再学習を伴わない実装レベルの改良**の効果を検証する。

1. **視覚情報とDOM構造の統合**
   - 行動選択のロバスト性向上
2. **失敗要因の分解分析**
   - 知覚・計画・動作の各フェーズでの分析
3. **費用対効果の高い設計指針の導出**
   - 各機能改善を個別に適用し、成功率への寄与を定量化

---

## 3. 提案手法：アプローチ概要

GPT-4oを推論エンジンとし、SoM (Set-of-Mark) ベースのエージェントに以下の機能拡張を独立して適用・評価する。

1. **基盤安定化** (`main`): 再現性確保、環境整備
2. **ページ内検索強化** (`fix_pagefind`): JSベースの検索・可視化
3. **失敗時リトライ** (`failure-retry`): 失敗検出時のみ局所的再試行
4. **自己修正** (`self-correction`): 失敗時の診断・方針再構築
5. **ROI/OCR/DOM追加観測** (`roi-ocr-dom`): 局所情報の高解像度化
6. **視覚-DOMアラインメント** (`visual-dom-alignment`): 要素対応の補強
7. **階層的計画** (`hierarchical-plan`): サブゴール分解

---

## 4. 主要な提案機能 (1/3)

### 視覚-DOMアラインメント (`visual-dom-alignment`)
- **課題**: 視覚上の配置（SoM画像）とDOM構造の意味的対応が曖昧で、クリック対象を取り違える。
- **手法**: クリック候補に対し、**近傍テキスト・属性・相対位置**などの軽量な情報を付与。
- **目的**: 「見た目」と「意味」の橋渡しを行い、選択精度を向上させる。

### 失敗時リトライ (`failure-retry`)
- **課題**: 一度の誤操作でタスクが破綻する。
- **手法**: エラー検出時（遷移失敗等）のみ、観測を更新して候補を選び直す。
- **利点**: トークン消費を常時増やさず、偶発的な失敗を吸収。

---

## 4. 主要な提案機能 (2/3)

### 階層的計画 (`hierarchical-plan`)
- **手法**: タスクを「探索→絞り込み→確定」等のサブゴールに分解。
- **目的**: 長期タスクにおける方針の揺らぎを抑制。

### 自己修正 (`self-correction`)
- **手法**: 失敗時に「診断フェーズ」を挟み、原因特定と代替案生成を行う。
- **目的**: 誤った仮説の固定化を防ぐ。

---

## 4. 主要な提案機能 (3/3)

### ROI/OCR/DOM (`roi-ocr-dom`)
- **手法**: 必要な箇所だけROIで追加情報（局所OCR、要素レベルDOM/属性など）を取り、確信度を上げる。
- **目的**: SoM画像のみで判断材料が足りず、誤クリック・誤抽出が起きるのを防ぐ。

### ページ検索 (`fix_pagefind`)
- **手法**: JavaScriptによるページ内検索の実装。
- **目的**: スクロールなどの操作を行わないと見つけられないキーワードの探索・抽出の精度を上げる。

---

## 5. 実験設定

- **評価環境**: VisualWebArena (VWA)
- **対象ドメイン**:
  - Shopping
  - Reddit
  - Classifieds
- **タスク**: 各ドメインから代表的な12タスクを選定（計36タスク）
- **モデル**: GPT-4o
- **指標**: タスク成功率 (Success Rate)

---

## 6. 実験結果：成功率

| Branch | Shopping | Reddit | Classifieds |
| :--- | :---: | :---: | :---: |
| **main** (Baseline) | 0/12 | 0/12 | 0/12 |
| fix\_pagefind | 0/12 | 0/12 | 0/12 |
| failure-retry | 0/12 | 0/12 | **1/12** |
| self-correction | 0/12 | 0/12 | 0/12 |
| roi-ocr-dom | 0/12 | 0/12 | 0/12 |
| **visual-dom-alignment** | **1/12** | **1/12** | **1/12** |
| hierarchical-plan | **1/12** | 0/12 | 0/12 |

- **visual-dom-alignment** が全ドメインで一貫して改善を示した。
- 高度な推論（自己修正等）は、ベースラインでは効果が見られなかった。

---

## 7. 考察

- **視覚-DOMアラインメントの有効性**
  - VWAの主要な失敗要因は「推論能力不足」よりも **「視覚要素とDOM要素の対応不一致」** にある可能性が高い。
  - 軽量なアラインメント信号を加えるだけで、最も安定した改善が得られた。

- **高度な機能の限界**
  - 自己修正（Self-correction）や階層的計画（Hierarchical-plan）は、**基盤となる「正しくwebページを認識する能力」** が低い状態では機能しない（空回りする）。

- **ドメイン依存性**
  - `failure-retry` はClassifiedsのような、回復可能な失敗を含むドメインでのみ有効。

---

## 8. まとめ

VisualWebArenaを用いたWebエージェントの実装改良評価を実施。

**結論**
   - **視覚とDOMの軽量アラインメント (`visual-dom-alignment`)** が、最も安定して成功率を改善する。
   - 複雑な推論や計画機能の実装は、基礎的な操作精度（Grounding）が確保されない限り効果が限定的である。

---

# ご清聴ありがとうございました