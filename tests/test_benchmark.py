"""APIを使わず、計測・保存・再開の振る舞いを検証する。"""
import json
from types import SimpleNamespace as NS

import pytest
from google.genai import errors

from app import benchmark as b


def response(text="テスト専用応答", usage=True):
    return NS(text=text, model_version="returned-model", usage_metadata=NS(
        prompt_token_count=11, candidates_token_count=23,
        thoughts_token_count=7, total_token_count=41,
        cached_content_token_count=None,
    ) if usage else None)


def test_measure_records_duration_and_separate_thinking_tokens():
    ticks = iter([10.0, 12.5])
    result = b.measure(lambda m, q: response(), "m", "q", clock=lambda: next(ticks))
    assert result["elapsed_seconds"] == 2.5
    assert result["input_tokens"] == 11
    assert result["output_tokens"] == 23
    assert result["thinking_tokens"] == 7
    assert result["total_tokens"] == 41
    assert result["status"] == "ok"


def test_missing_usage_is_unknown_not_zero():
    result = b.measure(lambda m, q: response(usage=False), "m", "q")
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_api_error_does_not_save_sensitive_message():
    def fail(m, q):
        raise errors.ClientError(429, {"error": {"message": "SECRET-EXAMPLE"}})
    result = b.measure(fail, "m", "q")
    assert result["status"] == "error"
    assert result["error_code"] == 429
    assert "SECRET-EXAMPLE" not in json.dumps(result)


def test_empty_response_is_not_success():
    result = b.measure(lambda m, q: response(text=""), "m", "q")
    assert result["status"] == "empty"


def test_resume_skips_completed_attempts_and_preserves_log(tmp_path):
    first = b.run_experiment(tmp_path, ["a", "b"], 3, 0, lambda m, q: response(), limit=2)
    original = (tmp_path / "results.jsonl").read_bytes()
    assert len(first) == 2
    result = b.run_experiment(tmp_path, ["a", "b"], 3, 0, lambda m, q: response())
    assert len(result) == 18
    assert len({r["trial_id"] for r in result}) == 18
    assert (tmp_path / "results.jsonl").read_bytes().startswith(original)
    def no_more_calls(m, q):
        pytest.fail("完了済みの実験でAPIを再呼び出した")
    assert len(b.run_experiment(tmp_path, ["a", "b"], 3, 0, no_more_calls)) == 18


def test_changed_configuration_is_rejected(tmp_path):
    b.run_experiment(tmp_path, ["a", "b"], 3, 0, lambda m, q: response(), limit=1)
    with pytest.raises(ValueError, match="条件"):
        b.run_experiment(tmp_path, ["a", "c"], 3, 0, lambda m, q: response())


def test_429_is_saved_and_stops_batch_without_retry(tmp_path):
    def fail(m, q):
        raise errors.ClientError(429, {"error": {"message": "quota"}})
    rows = b.run_experiment(tmp_path, ["a", "b"], 3, 0, fail)
    assert len(rows) == 1
    assert rows[0]["error_code"] == 429
    assert json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))["status"] == "error"


def test_interval_is_outside_measured_time(tmp_path):
    waits = []
    rows = b.run_experiment(tmp_path, ["a", "b"], 1, 15, lambda m, q: response(), sleep=waits.append, limit=2)
    assert waits == [15]
    assert all(r["elapsed_seconds"] < 1 for r in rows)


def test_corrupt_log_is_not_silently_discarded(tmp_path):
    b.run_experiment(tmp_path, ["a", "b"], 1, 0, lambda m, q: response(), limit=1)
    with (tmp_path / "results.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"interrupted":')
    with pytest.raises(ValueError, match="ログ"):
        b.run_experiment(tmp_path, ["a", "b"], 1, 0, lambda m, q: response())


def test_missing_final_newline_is_rejected_before_append(tmp_path):
    b.run_experiment(tmp_path, ["a", "b"], 1, 0, lambda m, q: response(), limit=1)
    log = tmp_path / "results.jsonl"
    log.write_text(log.read_text(encoding="utf-8").rstrip(), encoding="utf-8")
    original = log.read_bytes()
    with pytest.raises(ValueError, match="ログ"):
        b.run_experiment(tmp_path, ["a", "b"], 1, 0, lambda m, q: response())
    assert log.read_bytes() == original


def test_interruption_preserves_saved_results_and_releases_lock(tmp_path):
    calls = 0
    def interrupted(m, q):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return response()
    with pytest.raises(KeyboardInterrupt):
        b.run_experiment(tmp_path, ["a", "b"], 1, 0, interrupted)
    assert len(b.read_records(tmp_path / "results.jsonl")) == 1
    assert not (tmp_path / ".running").exists()


def test_concurrent_run_is_blocked(tmp_path):
    (tmp_path / ".running").touch()
    with pytest.raises(ValueError, match="実行中"):
        b.run_experiment(tmp_path, ["a", "b"], 1, 0, lambda m, q: pytest.fail("API called"))


def test_transport_failure_is_recorded_without_details():
    import httpx
    def fail(m, q):
        raise httpx.ReadTimeout("SECRET-EXAMPLE")
    result = b.measure(fail, "m", "q")
    assert result["status"] == "error"
    assert result["error_type"] == "ReadTimeout"
    assert "SECRET-EXAMPLE" not in json.dumps(result)


@pytest.mark.parametrize("models,repeats,interval", [([], 3, 1), (["a", "a"], 3, 1), (["a"], 0, 1), (["a"], 3, -1), (["a"], 3, float("nan"))])
def test_invalid_configuration_fails_before_call(tmp_path, models, repeats, interval):
    with pytest.raises(ValueError):
        b.run_experiment(tmp_path, models, repeats, interval, lambda m, q: pytest.fail("API called"))
