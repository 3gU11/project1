import argparse
import os
from pathlib import Path


def fmt_kb(size: int) -> str:
    return f"{size / 1024:.2f} KB"


def collect_assets(dist_assets: Path) -> list[tuple[str, int]]:
    if not dist_assets.exists():
        return []
    items: list[tuple[str, int]] = []
    for p in dist_assets.iterdir():
        if p.is_file():
            items.append((p.name, p.stat().st_size))
    return sorted(items, key=lambda x: x[1], reverse=True)


def build_report(rows: list[tuple[str, int]], top_n: int) -> str:
    total = sum(size for _, size in rows)
    js_total = sum(size for name, size in rows if name.endswith(".js"))
    css_total = sum(size for name, size in rows if name.endswith(".css"))
    lines = [
        "# 前端构建性能基线",
        "",
        f"- 总文件数: {len(rows)}",
        f"- 资产总大小: {fmt_kb(total)}",
        f"- JS 总大小: {fmt_kb(js_total)}",
        f"- CSS 总大小: {fmt_kb(css_total)}",
        "",
        f"## Top {top_n} 资源",
        "",
        "| 文件 | 大小 |",
        "|---|---|",
    ]
    for name, size in rows[:top_n]:
        lines.append(f"| {name} | {fmt_kb(size)} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dist assets baseline report")
    parser.add_argument("--dist", default="frontend/dist/assets", help="dist assets directory")
    parser.add_argument("--top", type=int, default=20, help="top N assets in report")
    parser.add_argument("--out", default="frontend/dist/perf-baseline.md", help="output markdown file")
    args = parser.parse_args()

    dist_assets = Path(args.dist)
    rows = collect_assets(dist_assets)
    if not rows:
        print(f"[perf] no assets found: {dist_assets}")
        return 1

    report = build_report(rows, max(1, args.top))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"[perf] baseline written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
