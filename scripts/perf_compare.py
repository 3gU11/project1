import argparse
import re
from pathlib import Path


METRIC_KEYS = {
    "assets_total_kb": "资产总大小",
    "js_total_kb": "JS 总大小",
    "css_total_kb": "CSS 总大小",
}


def parse_baseline(md_path: Path) -> dict[str, float]:
    text = md_path.read_text(encoding="utf-8")
    result: dict[str, float] = {}
    for key, label in METRIC_KEYS.items():
      pattern = rf"- {re.escape(label)}:\s*([0-9]+(?:\.[0-9]+)?)\s*KB"
      m = re.search(pattern, text)
      if not m:
          raise ValueError(f"missing metric: {label} in {md_path}")
      result[key] = float(m.group(1))
    return result


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100.0


def build_report(current: dict[str, float], previous: dict[str, float], previous_path: str) -> str:
    lines = [
        "# 前端性能基线对比",
        "",
        f"- 对比基线: {previous_path}",
        "",
        "| 指标 | 当前 (KB) | 上次 (KB) | 变化 (KB) | 变化率 |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, label in METRIC_KEYS.items():
        c = current[key]
        p = previous[key]
        diff = c - p
        pct = pct_change(c, p)
        lines.append(f"| {label} | {c:.2f} | {p:.2f} | {diff:+.2f} | {pct:+.2f}% |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two perf baseline markdown files")
    parser.add_argument("--current", default="frontend/dist/perf-baseline.md")
    parser.add_argument("--previous", required=True)
    parser.add_argument("--out", default="frontend/dist/perf-compare.md")
    args = parser.parse_args()

    current_path = Path(args.current)
    previous_path = Path(args.previous)
    if not current_path.exists():
        print(f"[perf] current baseline not found: {current_path}")
        return 1
    if not previous_path.exists():
        print(f"[perf] previous baseline not found: {previous_path}")
        return 1

    current = parse_baseline(current_path)
    previous = parse_baseline(previous_path)
    report = build_report(current, previous, str(previous_path))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"[perf] compare written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
