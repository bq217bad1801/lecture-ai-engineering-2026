"""第1回の比較実験。結果を1試行ずつ保存し、同じコマンドで再開する。"""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import time

import httpx
from google import genai
from google.genai import errors, types

from app.config import get_api_key

QUESTIONS = [
    {"id": "lora", "text": "LoRAとは何ですか？"},
    {"id": "homework", "text": "AIE2026の講座の宿題にある「3レベル」とは何ですか？"},
    {"id": "lecture02", "text": "AIE2026の第2回では何を学びますか？"},
]
TOKEN_FIELDS = {
    "input_tokens": "prompt_token_count",
    "output_tokens": "candidates_token_count",
    "thinking_tokens": "thoughts_token_count",
    "total_tokens": "total_token_count",
    "cached_tokens": "cached_content_token_count",
}


def measure(generate, model, question, clock=time.perf_counter):
    """API境界の前後を測る。待ち時間・保存・集計は計測に含めない。"""
    result = dict(status="error", text=None, error_code=None, error_type=None,
                  returned_model=None, **dict.fromkeys(TOKEN_FIELDS))
    start = clock()
    try:
        response = generate(model, question)
        elapsed = clock() - start
    except (errors.APIError, httpx.HTTPError) as exc:
        result.update(elapsed_seconds=clock() - start,
                      error_code=getattr(exc, "code", None), error_type=type(exc).__name__)
        # 例外全文にはURL等が入り得るので、種類とHTTPコードだけ記録する。
        return result
    result.update(elapsed_seconds=elapsed, text=response.text,
                  returned_model=getattr(response, "model_version", None))
    result["status"] = "ok" if result["text"] and result["text"].strip() else "empty"
    usage = response.usage_metadata
    for name, field in TOKEN_FIELDS.items():
        result[name] = getattr(usage, field, None)
    return result


def experiment_config(models, repeats, interval):
    if (not models or len(set(models)) != len(models)
            or any(not m.strip() for m in models) or repeats < 1
            or not math.isfinite(interval) or interval < 0):
        raise ValueError("モデルは空でない重複なしの一覧、回数は1以上、間隔は0以上の有限値にしてください。")
    return dict(schema_version=1, models=models, repeats=repeats, interval_seconds=interval,
                questions=QUESTIONS, order_seed=42, sdk_attempts=1,
                timeout_ms=120000, generation_config="model defaults; no temperature override")


def schedule(config):
    # 各ラウンドで順序を変え、常に特定モデルが最初になる偏りを減らす。
    # 乱数seedは実行順序用。LLMの回答を固定するseedではない。
    rng = random.Random(config["order_seed"])
    tasks = []
    for repeat in range(1, config["repeats"] + 1):
        batch = [dict(trial_id=f"r{repeat}-m{mi}-{q['id']}", repeat=repeat,
                      model=model, question_id=q["id"], question=q["text"])
                 for mi, model in enumerate(config["models"]) for q in config["questions"]]
        rng.shuffle(batch)
        tasks.extend(batch)
    return tasks


def read_records(path):
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            raise ValueError("末尾の改行がありません。追記すると次の試行と連結してしまいます。")
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        ids = [r["trial_id"] for r in records]
        if len(ids) != len(set(ids)):
            raise ValueError("重複した試行ID")
        return records
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("ログが破損または重複しています。元ファイルを保管して確認してください。") from exc


def environment_info():
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return dict(python=platform.python_version(), google_genai=version("google-genai"),
                git_commit=commit)


def run_experiment(path, models, repeats, interval, generate, sleep=time.sleep, limit=None):
    config = experiment_config(models, repeats, interval)
    if limit is not None and limit < 1:
        raise ValueError("limitは1以上にしてください。")
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    # 同時起動で二重測定しない。強制終了後に残った場合は手順書に沿って確認。
    lock = path / ".running"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("実験が実行中、または.runningが残っています。二重起動しないでください。") from exc
    os.close(lock_fd)
    try:
        manifest = path / "config.json"
        log = path / "results.jsonl"
        if manifest.exists():
            if json.loads(manifest.read_text(encoding="utf-8")) != config:
                raise ValueError("保存済みの実験条件と異なります。別の--outputを指定してください。")
        elif log.exists():
            raise ValueError("ログに対応するconfig.jsonがありません。別の出力先を指定してください。")
        else:
            manifest.write_text(json.dumps(config, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        rows = read_records(log)
        tasks = schedule(config)
        by_id = {t["trial_id"]: t for t in tasks}
        for row in rows:
            task = by_id.get(row["trial_id"])
            if task is None or any(row.get(k) != v for k, v in task.items()):
                raise ValueError("ログと実験条件が一致しません。")
        done = {r["trial_id"] for r in rows}
        pending = [t for t in tasks if t["trial_id"] not in done]
        env = environment_info() if pending else {}
        new_count = 0
        for task in pending:
            if limit is not None and new_count >= limit:
                break
            if rows:
                sleep(interval)
            stamp = datetime.now(timezone.utc).isoformat()
            result = measure(generate, task["model"], task["question"])
            row = dict(**task, **result, started_at_utc=stamp, environment=env)
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False)+"\n")
                f.flush()
                os.fsync(f.fileno())
            rows.append(row)
            new_count += 1
            print(f"{len(rows)}/{len(tasks)} {task['trial_id']} {task['model']} "
                  f"{result['status']} {result['elapsed_seconds']:.2f}s", flush=True)
            if result["error_code"] in (400, 401, 403, 404, 429):
                print("APIエラーを記録して停止しました。上限・モデル・権限を確認してください。")
                break
        return rows
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True, help="AI Studioで利用可能と確認したモデルID")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--interval", type=float, default=15, help="前の呼び出し完了から次の開始までの待機秒数")
    parser.add_argument("--output", type=Path, default=Path("lectures/01/results/main"))
    parser.add_argument("--limit", type=int, help="今回新たに実行する最大試行数")
    parser.add_argument("--dry-run", action="store_true", help="実行順を表示。APIも保存も行わない")
    args = parser.parse_args()
    try:
        config = experiment_config(args.models, args.repeats, args.interval)
        if args.limit is not None and args.limit < 1:
            raise ValueError("limitは1以上にしてください。")
        if args.dry_run:
            print(json.dumps(schedule(config), ensure_ascii=False, indent=2))
            return
        # SDKの隠れた再試行を禁止し、1試行=1リクエストにする。
        options = types.HttpOptions(timeout=120000, retry_options=types.HttpRetryOptions(attempts=1))
        with genai.Client(api_key=get_api_key(), http_options=options) as client:
            rows = run_experiment(args.output, args.models, args.repeats, args.interval,
                                  lambda model, question: client.models.generate_content(model=model, contents=question),
                                  limit=args.limit)
        planned = len(schedule(config))
        print(f"記録済み {len(rows)}/{planned}、成功 {sum(r['status']=='ok' for r in rows)}。")
        if len(rows) < planned or any(r["status"] != "ok" for r in rows):
            raise SystemExit(2)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
