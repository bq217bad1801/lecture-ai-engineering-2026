import csv
import json

from app import benchmark_report as report


def row(i, status="ok", seconds=2, tokens=10):
    return dict(trial_id=str(i), model="m", question_id="q", question="質問", repeat=i,
                status=status, elapsed_seconds=seconds, input_tokens=tokens,
                output_tokens=tokens, thinking_tokens=None, total_tokens=tokens,
                text="テスト専用応答", error_code=None)


def test_summary_excludes_error_and_does_not_treat_missing_usage_as_zero():
    result = report.summarize([row(1, seconds=1), row(2, seconds=5, tokens=None), row(3, "error", 100)])
    assert result[0]["attempts"] == 3
    assert result[0]["successes"] == 2
    assert result[0]["elapsed_median"] == 3
    assert result[0]["elapsed_min"] == 1
    assert result[0]["elapsed_max"] == 5
    assert result[0]["output_tokens_median"] == 10
    assert result[0]["output_tokens_n"] == 1


def test_all_failures_have_no_success_statistics():
    result = report.summarize([row(1, "error")])[0]
    assert result["successes"] == 0
    assert result["elapsed_median"] is None
    assert report.summarize([]) == []


def test_report_preserves_manual_evaluation_and_appends_new_trials(tmp_path):
    log = tmp_path / "results.jsonl"
    log.write_text(json.dumps(row(1), ensure_ascii=False)+"\n", encoding="utf-8")
    report.create_report(tmp_path)
    evaluation = tmp_path / "evaluation.csv"
    with evaluation.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0]["rating"] = "正しい"
    rows[0]["reason"] = "用語集と一致"
    with evaluation.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row(2))+"\n")
    report.create_report(tmp_path)
    with evaluation.open(encoding="utf-8-sig", newline="") as f:
        saved = list(csv.DictReader(f))
    assert len(saved) == 2
    assert saved[0]["rating"] == "正しい"
    assert saved[0]["reason"] == "用語集と一致"
    assert saved[1]["rating"] == ""
    assert (tmp_path / "summary.csv").exists()
    assert (tmp_path / "comparison.svg").exists()
    assert "2" in (tmp_path / "summary.md").read_text(encoding="utf-8")
