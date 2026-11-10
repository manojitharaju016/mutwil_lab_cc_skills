#!/usr/bin/env python3
"""
Render a styled progress block for kg-constructor runs.

Usage:
    echo '{"kind": "banner", ...}' | render_progress.py
    render_progress.py --state path/to/state.json

State JSON schema (all kinds use a common shape; only relevant fields are read):

{
  "kind":         "banner" | "wave" | "heartbeat" | "fail" | "final",
  "input":        str,
  "output_dir":   str,
  "model":        str,
  "max_concurrent": int,
  "waves_total":  int,
  "wave_idx":     int,
  "sections_total": int,
  "sections_done":  int,
  "sections_ok":    int,
  "sections_fail":  int,
  "sections_retried": int,
  "triples_total":  int,
  "wave_walltime_s": float,
  "wave_walltime_median_s": float,
  "throughput_per_min": float,
  "eta_remaining_s":   float,
  "eta_finish_iso":    str,
  "papers_total": int,
  "wave_subagents_done": int,
  "wave_subagents_total": int,
  "wave_oldest_age_s":   float,
  "spinner_idx": int,
  "custom_id": str,
  "reason":    str,
  "retry_num": int,
  "retry_max": int,
  "validation_status": str,
  "validation_violations": int,
  "output_paths": {"per_section": str, "per_paper": str, "csv_dir": str,
                   "merged_csv": str, "metadata": str, "run_log": str}
}
"""

import argparse
import json
import sys
from datetime import datetime


BAR_WIDTH = 38
FILL_CH = "▓"
EMPTY_CH = "░"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def bar(frac: float, width: int = BAR_WIDTH) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return FILL_CH * filled + EMPTY_CH * (width - filled)


def pct(n, d) -> str:
    if not d:
        return "  0.0%"
    return f"{(100.0 * n / d):5.1f}%"


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


def fmt_hms(seconds) -> str:
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "—"
    if s < 0:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:d}h {m:02d}m {sec:02d}s"
    if m:
        return f"{m:d}m {sec:02d}s"
    return f"{sec:d}s"


def short_path(p: str, width: int = 60) -> str:
    if not p:
        return ""
    if len(p) <= width:
        return p
    return "…" + p[-(width - 1):]


def render_banner(s: dict) -> str:
    title = "kg-constructor  •  run"
    lines = [
        "╔" + "═" * 74 + "╗",
        f"║{title:^74}║",
        "╠" + "═" * 74 + "╣",
        f"║  Input:        {short_path(s.get('input',''), 56):<56}  ║",
        f"║  Output:       {short_path(s.get('output_dir',''), 56):<56}  ║",
        f"║  Papers:       {fmt_int(s.get('papers_total', 0)):<8}   "
        f"Sections to extract:   {fmt_int(s.get('sections_total', 0)):<20} ║",
        f"║  Model:        {s.get('model','')[:24]:<24}   "
        f"Max concurrent:  {str(s.get('max_concurrent','')):<6}      ║",
        f"║  Waves:        {fmt_int(s.get('waves_total', 0)):<55}     ║",
        "╚" + "═" * 74 + "╝",
    ]
    return "\n".join(lines)


def render_wave(s: dict) -> str:
    sec_done = s.get('sections_done', 0)
    sec_total = s.get('sections_total', 0)
    sec_frac = (sec_done / sec_total) if sec_total else 0.0
    triples = s.get('triples_total', 0)
    triples_target = max(sec_total * 10, 1)
    tri_frac = min(1.0, triples / triples_target)
    eta_remaining = float(s.get('eta_remaining_s') or 0.0)
    eta_total_est = max(eta_remaining + 1.0, 1.0)
    eta_frac = max(0.0, min(1.0, 1.0 - eta_remaining / eta_total_est)) if eta_remaining else 1.0

    avg_per_sec = (triples / sec_done) if sec_done else 0.0

    lines = [
        "┌" + "─" * 74 + "┐",
        f"│  kg-constructor   ·   wave  {s.get('wave_idx',0):>3} / {s.get('waves_total',0):<3}"
        f"{' ' * (74 - 38)}│",
        "├" + "─" * 74 + "┤",
        "│" + " " * 74 + "│",
        f"│   Sections   {bar(sec_frac)}  {fmt_int(sec_done)} / {fmt_int(sec_total)}  {pct(sec_done, sec_total)}  │",
        f"│   Triples    {bar(tri_frac)}  {fmt_int(triples):<11} (≈ {avg_per_sec:4.1f}/sec)  │",
        "│" + " " * 74 + "│",
        f"│   This wave   ✓ {s.get('sections_ok',0):<4} ✗ {s.get('sections_fail',0):<4} ↻ {s.get('sections_retried',0):<4}"
        f"  wall {fmt_hms(s.get('wave_walltime_s', 0)):<9} median {fmt_hms(s.get('wave_walltime_median_s', 0)):<9}│",
        f"│   Cumulative  ✓ {s.get('cum_ok',0):<5} ✗ {s.get('cum_fail',0):<5} ↻ {s.get('cum_retried',0):<5}"
        f" retries left {s.get('retries_left', 0)} / {s.get('retries_budget', 0)} in budget  │",
        "│" + " " * 74 + "│",
        f"│   Throughput   {s.get('throughput_per_min', 0.0):>5.1f} sections / min   (rolling 5-wave mean)         │",
        f"│   ETA          {bar(eta_frac, 20)}  remaining  {fmt_hms(eta_remaining):<14}            │",
        f"│{' ' * 39}finish at  {s.get('eta_finish_iso',''):<22}  │",
        "│" + " " * 74 + "│",
        "└" + "─" * 74 + "┘",
    ]
    return "\n".join(lines)


def render_heartbeat(s: dict) -> str:
    idx = int(s.get('spinner_idx', 0)) % len(SPINNER)
    spin = SPINNER[idx]
    return (
        f"{spin}  wave {s.get('wave_idx',0)} still in flight   ·   "
        f"{s.get('wave_subagents_done',0)} / {s.get('wave_subagents_total',0)} subagents done   ·   "
        f"oldest {fmt_hms(s.get('wave_oldest_age_s', 0))}"
    )


def render_fail(s: dict) -> str:
    return (
        f"   ✗ wave {s.get('wave_idx',0)} · {s.get('custom_id','')[:48]} · "
        f"{s.get('reason','')[:40]} · retry {s.get('retry_num',0)}/{s.get('retry_max',2)}"
    )


def render_final(s: dict) -> str:
    paths = s.get('output_paths', {}) or {}
    lines = [
        "╔" + "═" * 74 + "╗",
        f"║{'kg-constructor  •  run complete':^74}║",
        "╠" + "═" * 74 + "╣",
        f"║  Sections processed:   {fmt_int(s.get('sections_done',0))}/"
        f"{fmt_int(s.get('sections_total',0)):<10}   "
        f"Triples extracted: {fmt_int(s.get('triples_total',0)):<12} ║",
        f"║  Papers:               {fmt_int(s.get('papers_total',0)):<10}   "
        f"Waves: {fmt_int(s.get('waves_total',0)):<10}                ║",
        f"║  Total wall-clock:     {fmt_hms(s.get('total_walltime_s', 0)):<25}                ║",
        f"║  Throughput:           {s.get('throughput_per_min', 0.0):>5.1f} sec/min      Retries: "
        f"{fmt_int(s.get('cum_retried',0)):<12}     ║",
        f"║  Failures:             {fmt_int(s.get('cum_fail',0)):<10}   "
        f"Validation: {s.get('validation_status','pending'):<14}     ║",
        "╠" + "═" * 74 + "╣",
        f"║  per_section/  {short_path(paths.get('per_section',''), 56):<56}  ║",
        f"║  per_paper/    {short_path(paths.get('per_paper',''), 56):<56}  ║",
        f"║  csv/          {short_path(paths.get('csv_dir',''), 56):<56}  ║",
        f"║  merged_kg.csv {short_path(paths.get('merged_csv',''), 56):<56}  ║",
        f"║  metadata.json {short_path(paths.get('metadata',''), 56):<56}  ║",
        f"║  run.log       {short_path(paths.get('run_log',''), 56):<56}  ║",
        "╚" + "═" * 74 + "╝",
    ]
    if s.get('validation_violations'):
        lines.append(
            f"⚠  validation reported {fmt_int(s['validation_violations'])} rule violations "
            f"— see {short_path(paths.get('run_log',''))}"
        )
    return "\n".join(lines)


RENDERERS = {
    "banner": render_banner,
    "wave": render_wave,
    "heartbeat": render_heartbeat,
    "fail": render_fail,
    "final": render_final,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", help="Path to state JSON. If omitted, read stdin.")
    ap.add_argument("--kind", help="Override the 'kind' field of the state JSON.")
    args = ap.parse_args()

    if args.state:
        text = open(args.state, "r", encoding="utf-8").read()
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("ERROR: empty state JSON", file=sys.stderr)
        sys.exit(2)
    try:
        state = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid state JSON: {e}", file=sys.stderr)
        sys.exit(2)

    kind = args.kind or state.get("kind", "")
    fn = RENDERERS.get(kind)
    if not fn:
        print(f"ERROR: unknown kind: {kind!r}. expected one of {list(RENDERERS)}", file=sys.stderr)
        sys.exit(2)
    print(fn(state))


if __name__ == "__main__":
    main()
