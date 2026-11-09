"""実測JSONLから集計と評価シートを作る。API呼び出しはしない。"""
import argparse
from collections import defaultdict
import csv
from html import escape
from pathlib import Path
from statistics import median

from app.benchmark import read_records


def summarize(records):
    groups = defaultdict(list)
    for row in records:
        groups[(row["model"], row["question_id"])].append(row)
    summary = []
    for (model, question), rows in sorted(groups.items()):
        success = [r for r in rows if r["status"] == "ok"]
        item = dict(model=model, question_id=question, attempts=len(rows), successes=len(success),
                    failures=len(rows)-len(success))
        for field, prefix in [("elapsed_seconds", "elapsed"), ("input_tokens", "input_tokens"),
                              ("output_tokens", "output_tokens"), ("thinking_tokens", "thinking_tokens"),
                              ("total_tokens", "total_tokens")]:
            values = [r[field] for r in success if r.get(field) is not None]
            item.update({prefix+"_n": len(values), prefix+"_median": median(values) if values else None,
                         prefix+"_min": min(values) if values else None,
                         prefix+"_max": max(values) if values else None})
        summary.append(item)
    return summary


def write_csv(path, rows, fields):
    # UTF-8 BOM付きならWindowsのExcelでも日本語を読みやすい。
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def update_evaluation(path, records):
    fields = ["trial_id", "model", "question_id", "repeat", "status", "rating", "reason", "source"]
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != fields:
                raise ValueError("評価CSVの列が変更されています。上書きせず終了します。")
            rows = list(reader)
    else:
        rows = []
    done = {r["trial_id"] for r in rows}
    for record in records:
        if record["trial_id"] not in done:
            rows.append({f: record.get(f, "") for f in fields})
    write_csv(path, rows, fields)


def chart_svg(summary):
    # 棒は中央値、横線は最小～最大。異なる単位は別パネルにする。
    width, label_width, panel_width = 1200, 370, 360
    height = 100 + max(len(summary), 1)*64
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<g font-family="sans-serif" font-size="13" fill="#182230">',
           '<text x="20" y="25">Observed successes only — bar: median; line: min–max</text>']
    for panel, (field, title) in enumerate([("elapsed", "API response time (s)"), ("output_tokens", "Output tokens (excludes thinking)")]):
        start = label_width + panel*410
        maximum = max((r[field+"_max"] or 0 for r in summary), default=1) or 1
        out.append(f'<text x="{start}" y="55">{title}</text>')
        for i, row in enumerate(summary):
            y = 85 + i*64
            if panel == 0:
                label = escape(f"{row['model']} / {row['question_id']} ({row['successes']}/{row['attempts']})")
                out.append(f'<text x="15" y="{y+16}">{label}</text>')
            med = row[field+"_median"]
            if med is None:
                out.append(f'<text x="{start}" y="{y+16}">N/A</text>')
                continue
            scale = (panel_width-70)/maximum
            lo, hi = row[field+"_min"]*scale, row[field+"_max"]*scale
            out.extend([f'<rect x="{start}" y="{y}" width="{med*scale:.2f}" height="24" fill="#4c83d1"/>',
                        f'<path d="M {start+lo:.2f},{y+12} H {start+hi:.2f}" stroke="#182230" stroke-width="2"/>',
                        f'<text x="{start+hi+8:.2f}" y="{y+17}">{med:.2f}</text>'])
    out.append('</g></svg>')
    return "\n".join(out)


def create_report(path):
    path = Path(path)
    records = read_records(path / "results.jsonl")
    if not records:
        raise ValueError("実測ログがありません。架空の集計は作成しません。")
    summary = summarize(records)
    update_evaluation(path / "evaluation.csv", records)
    write_csv(path / "summary.csv", summary, list(summary[0]))
    def fmt(value):
        return "不明" if value is None else f"{value:.2f}"
    lines = ["# 実測データの集計", "", "成功した応答のみを集計。欠損値は0に置き換えない。正確さは未評価。",
             "再実行すると本集計は更新される。考察はanswer.mdへ記入する。", "",
             "|モデル|質問|成功/試行|秒 中央値|秒 最小～最大|入力 中央値|出力 中央値|出力の有効件数|",
             "|---|---|---:|---:|---|---:|---:|---:|"]
    for r in summary:
        model = r['model'].replace('|', '\\|')
        lines.append(f"|{model}|{r['question_id']}|{r['successes']}/{r['attempts']}|{fmt(r['elapsed_median'])}|"
                     f"{fmt(r['elapsed_min'])}～{fmt(r['elapsed_max'])}|{fmt(r['input_tokens_median'])}|"
                     f"{fmt(r['output_tokens_median'])}|{r['output_tokens_n']}|")
    lines += ["", "![中央値と最小・最大の比較](comparison.svg)", "", "## 失敗・空応答", ""]
    for r in records:
        if r["status"] != "ok":
            lines.append(f"- {r['trial_id']}: {r['status']}, HTTP={r.get('error_code')}。成功時の統計から除外。")
    lines += ["", "## 回答原文（評価用）", ""]
    for r in records:
        lines += [f"### {r['trial_id']}", "", f"モデル: {r['model']} / 質問: {r['question']}", "",
                  "<pre>"+escape(r.get("text") or "（回答なし）")+"</pre>", ""]
    (path / "summary.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (path / "comparison.svg").write_text(chart_svg(summary), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        create_report(args.path)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"{args.path}: summary.csv / summary.md / comparison.svg / evaluation.csv を保存しました。")


if __name__ == "__main__":
    main()
