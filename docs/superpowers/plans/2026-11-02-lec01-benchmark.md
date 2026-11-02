# 第1回比較実験 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 発展課題を再現可能に実行し、実測に基づく提出物を作れるようにする。
**Architecture:** 計測・追記保存・再開をbenchmark.py、集計・評価シート・SVGをbenchmark_report.pyへ分離。API境界だけをテストで置き換える。
**Tech Stack:** 講座のPython 3.12、google-genai固定版、標準ライブラリ、pytest。
**Spec:** ../specs/2026-11-02-lec01-design.md

## Global Constraints
- 2モデル×3質問×3回、計18回が基本。実際のモデルは明示指定。
- 講座の依存バージョンを変更しない。APIキーやエラー詳細全文を保存しない。
- 中断・失敗時も既存の記録を保持。未実測の結果は生成しない。
- 新規に取得した独立コピーのlec01で作業し、元リポジトリへpushしない。

## Review Focus
- 途中再開で同じ試行を重複実行しない（Task 1）。
- 条件を変えたまま同じ出力先に追記しない（Task 1）。
- 欠けたトークン数を0と扱わない（Task 1, 2）。
- 429/503/空応答を成功集計へ混ぜない（Task 1, 2）。
- 評価シートを再生成しても手動評価を上書きしない（Task 2）。

### Task 1: 計測と保存
**Files:** app/benchmark.py, app/ask.py, tests/test_benchmark.py
**Interfaces:** measure(generate, model, question, clock) -> dict; run_experiment(path, models, repeats, interval, generate, sleep) -> list[dict]
- [x] API偽応答・実ファイルで時間、欠損値、エラー、再開、条件不一致を検証するテストを書き、未実装で失敗を確認する。
- [x] 計測、JSONL追記、設定照合、直列実行、再開、dry-runを実装する。
- [x] app/ask.pyでusage_metadataから入力・出力トークン数を表示する。
- [x] 新規テストと既存テストを実行し、環境依存で未実行ならその理由を記録する。

### Task 2: 集計と提出支援
**Files:** app/benchmark_report.py, tests/test_benchmark_report.py, lectures/01/experiment_guide.md, lectures/01/answer.md
**Interfaces:** summarize(records) -> list[dict]; create_report(path) -> None
- [x] 成功値のみの中央値、欠損、失敗のみ、空データ、評価保持をテストし、未実装で失敗を確認する。
- [x] CSV・Markdown・SVGと人が記入する評価CSVを生成する。元ログとanswer.mdは書き換えない。
- [x] 実行手順、コードの意味、上限の記録、考察方法、未実測の解答ひな形を書く。
- [x] 全テスト・CLI・差分・秘密情報混入を確認し、ユーザーに実行可能なファイルを渡す。

## Progress / rulings
- 承認済み設計の実装依頼に基づき、このセッションで継続実装する。
- 新規cloneを独立作業場所として使用。既存のユーザーコードは変更しない。
- 指定されたサブエージェントモデルgpt-5.6-solは利用可能一覧にないため、別モデルへ置換せず自己レビューする。

## 検証記録
- 2026-11-02: Python 3.12.16、固定依存のまま、pytest全34件成功（13.81秒）。
- 新規モジュールの未実装エラー、askの表示テスト失敗、改行欠損の再現失敗を確認してから実装・修正した。
- Windows sandboxの一時フォルダ権限を回避するため専用basetempを指定。既存MCPテストを含む全体検証は権限付き実行で成功。
- 自己レビューで末尾改行欠損時の追記によるログ破損を検出し、回帰テストを追加して修正した。
- 同時実行防止・中断時の保存維持・ネットワークエラーの詳細非保存も検証。
- CLI dry-runで18試行の計画を確認。SVGはテスト専用データを描画して目視確認。
- API実測・正確さの人手評価・完成したanswer.md・宿題提出PRは未実施。
- サブエージェントの許可モデルが利用できないため、独立レビューは行わず自己レビューとした。
