# 第1回 発展＋αの実行手順とコードの読み方

この手順はCodespacesのBashターミナル用。ローカルのPowerShellでは環境変数の書き方が異なる。
実験はまだ実行していない。自動テストで使う偽応答は提出データではない。

## 1. 環境を確認する

自分のforkでブランチを `lec01` に切り替え、Code → Codespaces → Create codespace on lec01を選ぶ。
すでにmainのCodespacesを作った場合は次を実行する。

```bash
git fetch origin
git switch lec01
uv sync --frozen
uv run pytest -q
uv run python -c 'import os; print("GEMINI_API_KEY: 登録済み" if os.getenv("GEMINI_API_KEY") else "GEMINI_API_KEY: 未登録")'
```

- `git switch` は作業ブランチを切り替える。mainを直接変更しないために使う。
- `uv sync --frozen` は講座のuv.lockにある依存バージョンを再現する。
- `pytest` はAPIを呼ばずにプログラムを検証する。テスト成功はGemini接続成功とは異なる。
- 最後のコマンドはキーの有無だけを表示する。`echo $GEMINI_API_KEY` は実行しない。
- Secret登録前にCodespacesを起動した場合は停止・再起動する。

## 2. モデルと無料枠を決める

[AI Studio](https://aistudio.google.com/) で使用プロジェクトのモデル利用可否と上限を確認する。
講義資料のモデル名や上限は固定値として信用せず、実行時に確認する。
講義の比較候補は `gemini-3.5-flash-lite` と `gemini-3.8-flash`。
利用不可なら利用可能な2モデルへ置き換え、変更理由をanswer.mdに記録する。

|確認する項目|モデルA|モデルB|
|---|---|---|
|モデルID|要記入|要記入|
|確認日時・利用tier|要記入|要記入|
|RPM（1分のリクエスト数）|要記入|要記入|
|TPM（1分の入力トークン数）|要記入|要記入|
|RPD（1日のリクエスト数）|要記入|要記入|
|当日の使用済み数・残り|要記入|要記入|

本実験は各モデル9回、計18回。演習・接続確認分も同日の利用枠を消費する。
15秒の待機は上限内であることを保証しない。RPMが小さければ `--interval` を増やす。
RPMだけでなくTPM・RPDにも注意する。上限を故意に超える負荷実験はしない。
上限はプロジェクト単位なので、別のAPIキーや別タブの利用も関係する。

## 3. 演習を実行する

モデルIDを確認してから設定する。以下は講義資料の候補を使った例。

```bash
export MODEL_A=gemini-3.5-flash-lite
export MODEL_B=gemini-3.8-flash
AIE_MODEL="$MODEL_A" uv run python -m app.ask "LoRAとは何ですか？"
AIE_MODEL="$MODEL_A" uv run python -m app.ask "AIE2026の講座の宿題にある「3レベル」とは何ですか？"
```

回答と `[tokens]` の表示を読み、answer.mdの演習欄へ記録する。
正しい意味は `data/glossary.json` の `homework-levels`。回答を実際に読んでから照合する。
`app/ask.py` はAPIの `usage_metadata` から入力・出力本文トークン数を取り出す。
トークンは文字数と同じではないため、文字数から推定しない。

## 4. 本実験を実行する

```bash
uv run python -m app.benchmark --models "$MODEL_A" "$MODEL_B" --dry-run
uv run python -m app.benchmark --models "$MODEL_A" "$MODEL_B" --interval 15
```

`--dry-run` は18試行の順序を表示するだけで、APIもファイル保存も行わない。
2番目のコマンドはAPIを使う。既定は3質問×3回、保存先は `lectures/01/results/main`。
最初の1回だけ確認したい場合は、2番目のコマンドに `--limit 1` を付ける。
その後同じコマンドから `--limit 1` だけを外すと、最初の1回を重複せず残りを実行できる。

途中停止はCtrl+C。再開は同じコマンドを使う。
すでに保存された失敗試行も再実行しない。失敗を都合よく成功に置き換えないためである。
429で停止したらAI Studioで分・日・プロジェクトの上限を確認し、解消後に再開する。
400/401/403/404はモデル名・キー・権限等を確認する。
モデル、質問、回数、待機秒数などの条件を変える場合は `--output lectures/01/results/revised` のように別フォルダを使う。
異なる条件のデータを同じ実験として混ぜない。

終了コード2は「未完了、または失敗・空応答を含む」。ログは保持されている。
再実験する場合は元ログを残し、別の出力先に保存して理由を記録する。
強制終了後に `.running` が残った場合は、他に実験プロセスがないことを確認してそのファイルだけを削除する。
破損ログの警告が出た場合は元ファイルを保管して確認し、勝手に行を削って再開しない。

## 5. 集計・評価する

```bash
uv run python -m app.benchmark_report lectures/01/results/main
```

|ファイル|用途|
|---|---|
|config.json|モデル・質問・回数・順序seed・待機・SDK再試行設定|
|results.jsonl|1行1試行の原記録。回答、秒数、使用量、日時、SDK版、実行時コミット|
|summary.csv|各条件の成功件数、中央値、最小・最大、有効な測定値の件数|
|summary.md|比較表・図・回答原文。生成物なので考察を書き込まない|
|comparison.svg|応答時間と出力本文トークン数の比較。棒は中央値、横線は最小～最大|
|evaluation.csv|人がrating・reason・sourceを入力する評価シート。再集計時も記入を保持|

正確さは以下の基準で回答全体を読んで判定する。単語が含まれるだけで正解にしない。

|質問|参照先|確認点|
|lora|data/glossary.jsonのlora・peft|元の重みを固定し、小さな低ランク行列を学習すること、学習パラメータ削減|
|homework|同ファイルのhomework-levels|基礎・実装・発展の3段階、どれか1つで完了|
|lecture02|data/lectures/02.mdと第2回資料|ファインチューニング・LoRAとColab演習。無関係な内容を断定していないか|

- 正しい：重要点が一致し、重要な誤りがない。
- 一部誤り：正しい説明もあるが、重要な不足や誤りがある。
- 誤り：中心となる説明が誤っている。
- 分からないと回答：情報不足を明示し、答えを断定していない。
- API失敗・空応答は評価対象外と書き、知識の誤りと区別する。

資料にない追加説明を単に誤りと決めつけず、確認できない場合は理由欄に「要確認」と残す。
資料は評価のためだけに読む。本実験のモデル入力には渡していない。

## 6. コードの意味と設計理由

`app/benchmark.py` を次の順で読むと処理を追いやすい。

1. `QUESTIONS`：辞書のリストに3問を定義する。短いIDで保存・集計時の対応を保つ。
2. `experiment_config`：条件を検証する。マイナスの待機時間やモデルの重複をAPI呼び出し前に防ぐ。
3. `schedule`：ループでモデル×質問×回数の組を作る。固定seedでラウンドごとに順序を混ぜ、順序を再現できるようにする。LLM出力を固定する設定ではない。
4. `measure`：`perf_counter()` の差で経過時間を測る。ネットワークやサーバー待ちを含むAPI応答全体であり、モデル内部だけの速度や最初のトークンまでの時間ではない。
5. `TOKEN_FIELDS`：APIの属性名と保存用の名前を対応づける。`None` は不明のまま保持する。推論用と出力本文のトークンを区別する。
6. `run_experiment`：既存IDを集合にして、未実行だけ処理する。試行ごとにJSONLへ追記し、flush/fsyncで保存する。APIが完了した直後かつ保存前に強制終了した場合は、呼び出し済みか判別できないため再開前に利用履歴を確認する。
7. `time.sleep`：呼び出し間隔を空ける。この待機時間はモデルの応答時間に含めない。
8. `HttpRetryOptions(attempts=1)`：SDKの内部再試行を無効化し、1試行に複数のリクエストが隠れないようにする。
9. `with genai.Client(...)`：通信資源を使い終わったら閉じる。

`benchmark_report.py` の `summarize` は成功応答だけを分類し、標準ライブラリの `statistics.median` で中央値を求める。
たとえば1秒・2秒・20秒なら中央値は2秒。平均だけより外れ値の影響を受けにくいが、20秒の待ち時間も利用者には重要なので最小・最大も併記する。

## 7. 考察と提出

answer.mdは実際のデータを見て埋める。少なくとも次を考察する。

- 同じ質問でモデルごとの時間・使用量・正確さはどう違ったか。
- 同じモデルでも3回でどの程度変わったか。差がなかった場合もそのまま書く。
- 長い回答だから遅い可能性と、モデル固有の速さを区別できるか。
- 高性能とされるモデルでも、未提供の講座情報を正しく答えられたか。
- RPM・TPM・RPDのうち何が制約になったか。429が出なくても、上限と試行数の関係を説明する。
- 3回という少ない反復、通信、サーバー混雑、モデル既定設定の違い、実施日時の影響。

`output_tokens / elapsed_seconds` を計算しても純粋な生成速度ではない。通信と待ち時間、推論時間を含むためである。
またトークン数だけで料金や品質の優劣は決められない。

```bash
git status --short
git add lectures/01/answer.md lectures/01/results/main
git diff --cached --stat
git diff --cached
git commit -m "第1回 発展課題の実測と考察"
git push -u origin lec01
```

差分にAPIキーが含まれないこと、answer.mdに未記入が残らないことを確認する。
GitHubでbase repositoryを自分のfork、baseをmain、compareをlec01にしてPRを作る。
授業側にPRのURLを登録する追加の指定があれば、その案内にも従う。
終わったらCodespacesをStopする。
講義資料に記載の締切は10月26日。遅延提出の扱いは講座の最新アナウンスを確認する。

## 参考

- 講座の lectures/01/problem.md と演習PDF p.14–16。
- [Google公式：レート制限](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Google公式：Python SDK](https://googleapis.github.io/python-genai/)
- 2026-11-02のローカル検証はPython 3.12.16、google-genai 2.31.0。依存バージョンはuv.lockのまま。
