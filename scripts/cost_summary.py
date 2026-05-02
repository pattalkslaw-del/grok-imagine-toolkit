#!/usr/bin/env python3
"""
cost_summary.py — Roll up the Grok Imagine cost log.

USAGE:
    cost_summary.py [options]

OPTIONS:
    --since DATE        only count entries on or after DATE (YYYY-MM-DD)
    --until DATE        only count entries on or before DATE (YYYY-MM-DD)
    --by {operation,model,date}    group total by this dimension
    --json              output as JSON instead of text

EXAMPLES:
    cost_summary.py
    cost_summary.py --since 2026-05-01
    cost_summary.py --by model
    cost_summary.py --by date --since 2026-04-01

Log file format (one row per call):
    ISO8601 | operation | model | params_summary | cost_ticks | $cost_usd | request_id
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import load_config


def parse_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    rows = []
    for line in log_path.read_text().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        try:
            rows.append({
                "timestamp": parts[0],
                "operation": parts[1],
                "model": parts[2],
                "params": parts[3],
                "cost_ticks": int(parts[4]),
                "cost_usd": float(parts[5].lstrip("$")),
                "request_id": parts[6],
                "date": parts[0][:10],
            })
        except (ValueError, IndexError):
            continue
    return rows


def filter_rows(rows, since=None, until=None):
    out = rows
    if since:
        out = [r for r in out if r["date"] >= since]
    if until:
        out = [r for r in out if r["date"] <= until]
    return out


def summarize(rows: list[dict], by: str = None) -> dict:
    total_ticks = sum(r["cost_ticks"] for r in rows)
    total_usd = total_ticks / 1e10
    summary = {
        "n_calls": len(rows),
        "total_ticks": total_ticks,
        "total_usd": round(total_usd, 4),
    }
    if by:
        groups = defaultdict(lambda: {"n": 0, "ticks": 0})
        for r in rows:
            key = r.get(by, "?")
            groups[key]["n"] += 1
            groups[key]["ticks"] += r["cost_ticks"]
        summary["groups"] = {
            k: {"n": v["n"], "usd": round(v["ticks"] / 1e10, 4)}
            for k, v in sorted(groups.items())
        }
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--by", choices=["operation", "model", "date"])
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    cfg = load_config()
    rows = parse_log(Path(cfg["GROK_COST_LOG"]))
    rows = filter_rows(rows, since=args.since, until=args.until)
    summary = summarize(rows, by=args.by)

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print(f"Calls: {summary['n_calls']}")
    print(f"Total: ${summary['total_usd']:.4f} ({summary['total_ticks']} ticks)")
    if "groups" in summary:
        print(f"\nBy {args.by}:")
        for k, v in summary["groups"].items():
            print(f"  {k:30s}  {v['n']:4d} calls  ${v['usd']:.4f}")


if __name__ == "__main__":
    main()
