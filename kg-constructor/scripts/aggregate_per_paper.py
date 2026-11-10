#!/usr/bin/env python3
"""
Group per-section JSON files into per-paper JSON files.

Inputs (relative to <output_dir>):
    json/per_section/<custom_id>.json     written by subagents
    metadata.json                         written by prepare_sections.py

Outputs:
    json/per_paper/<paper_id>.json        one per paper, with the structure
        {
          "paper_id": ..., "filename": ..., "title": ...,
          "journal": ..., "year": ..., "month": ...,
          "sections": {"<section>": [<triples>], ...},
          "total_triples": <int>,
          "missing_sections": [<section>, ...],
          "recovered_sections": [<section>, ...]
        }
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


REQUIRED_KEYS = (
    "source", "source_identifier", "source_type", "source_category",
    "source_extracted_definition", "source_generated_definition",
    "relationship", "relationship_category",
    "target", "target_identifier", "target_type", "target_category",
    "target_extracted_definition", "target_generated_definition",
    "species", "basis",
    "extracted_associated_process_or_pathway",
    "generated_associated_process_or_pathway",
    "relevant_citations",
)


def strip_fences(text: str) -> str:
    """Remove ```json ... ``` fences if a subagent added them despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl > 0:
            t = t[first_nl + 1 :]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def attempt_partial_json_recovery(raw: str):
    """
    Salvage relationship objects from a truncated JSON array.

    Returns (parsed_list, recovered_count) on success, or (None, 0) on failure.
    Mirrors extract_kg_csv.py:attempt_partial_json_recovery() logic.
    """
    if not raw:
        return None, 0
    text = strip_fences(raw)

    # Some models wrap the array in {"relationships": [...]}.
    wrapper_idx = text.find('"relationships"')
    if wrapper_idx >= 0:
        bracket_open = text.find('[', wrapper_idx)
        if bracket_open >= 0:
            text = text[bracket_open:]

    text = text.lstrip()
    if not text.startswith('['):
        return None, 0

    brace_depth = 0
    bracket_depth = 0
    in_string = False
    escape = False
    last_complete_object_end = -1

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0 and bracket_depth == 1:
                    last_complete_object_end = i
            elif ch == '[':
                bracket_depth += 1
            elif ch == ']':
                bracket_depth -= 1

    if last_complete_object_end < 0:
        return None, 0

    truncated = text[: last_complete_object_end + 1].rstrip()
    while truncated.endswith(','):
        truncated = truncated[:-1].rstrip()
    truncated += "\n]"

    try:
        parsed = json.loads(truncated)
        if isinstance(parsed, list):
            return parsed, len(parsed)
    except json.JSONDecodeError:
        pass
    return None, 0


def load_section_triples(json_path: Path):
    """Return (triples_list, was_recovered, was_skipped, raw_text)."""
    raw = json_path.read_text(encoding="utf-8", errors="replace")
    text = strip_fences(raw)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        recovered, _ = attempt_partial_json_recovery(raw)
        if recovered is not None:
            return recovered, True, False, raw
        return [], False, True, raw

    if isinstance(parsed, list):
        return parsed, False, False, raw

    if isinstance(parsed, dict) and isinstance(parsed.get("relationships"), list):
        return parsed["relationships"], False, False, raw

    return [], False, True, raw


def validate_triple(triple: dict) -> bool:
    """Drop malformed objects but keep the rest of the list."""
    if not isinstance(triple, dict):
        return False
    for key in ("source", "relationship", "target"):
        v = triple.get(key)
        if not isinstance(v, str) or not v.strip():
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output_dir",
                    help="Run output directory (must contain metadata.json and json/per_section/)")
    args = ap.parse_args()

    output_dir = Path(args.output_dir).resolve()
    metadata_path = output_dir / "metadata.json"
    per_section_dir = output_dir / "json" / "per_section"
    per_paper_dir = output_dir / "json" / "per_paper"

    if not metadata_path.is_file():
        print(f"ERROR: missing {metadata_path}", file=sys.stderr)
        sys.exit(2)
    if not per_section_dir.is_dir():
        print(f"ERROR: missing {per_section_dir}", file=sys.stderr)
        sys.exit(2)

    per_paper_dir.mkdir(parents=True, exist_ok=True)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    requests = metadata.get("requests", {})
    paper_id_to_filename = metadata.get("_paper_id_to_filename", {})

    grouped = defaultdict(lambda: {
        "filename": "", "title": "", "journal": "", "year": "", "month": "",
        "sections": defaultdict(list),
        "expected_sections": set(),
        "missing_sections": [],
        "recovered_sections": [],
        "skipped_sections": [],
        "dropped_triples": 0,
    })

    for custom_id, meta in requests.items():
        paper_id = meta.get("paper_id")
        if not paper_id:
            continue
        section = meta.get("section", "")
        bucket = grouped[paper_id]
        bucket["filename"] = meta.get("filename", "")
        bucket["title"] = meta.get("title", "")
        bucket["journal"] = meta.get("journal", "")
        bucket["year"] = meta.get("year", "")
        bucket["month"] = meta.get("month", "")
        bucket["expected_sections"].add(section)

        json_path = per_section_dir / f"{custom_id}.json"
        if not json_path.is_file():
            bucket["missing_sections"].append(section)
            continue

        triples, recovered, skipped, _raw = load_section_triples(json_path)
        if skipped:
            bucket["skipped_sections"].append(section)
            continue
        if recovered:
            bucket["recovered_sections"].append(section)

        clean_triples = []
        for t in triples:
            if validate_triple(t):
                clean_triples.append(t)
            else:
                bucket["dropped_triples"] += 1

        bucket["sections"][section].extend(clean_triples)

    papers_written = 0
    total_triples = 0
    for paper_id, bucket in grouped.items():
        sections_obj = {k: v for k, v in bucket["sections"].items()}
        triple_count = sum(len(v) for v in sections_obj.values())
        total_triples += triple_count

        paper_out = {
            "paper_id": paper_id,
            "filename": bucket["filename"] or paper_id_to_filename.get(paper_id, ""),
            "title": bucket["title"],
            "journal": bucket["journal"],
            "year": bucket["year"],
            "month": bucket["month"],
            "sections": sections_obj,
            "total_triples": triple_count,
            "missing_sections": sorted(bucket["missing_sections"]),
            "recovered_sections": sorted(bucket["recovered_sections"]),
            "skipped_sections": sorted(bucket["skipped_sections"]),
            "dropped_triples": bucket["dropped_triples"],
        }
        out_path = per_paper_dir / f"{paper_id}.json"
        out_path.write_text(
            json.dumps(paper_out, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        papers_written += 1

    summary = {
        "papers_written": papers_written,
        "total_triples": total_triples,
        "per_paper_dir": str(per_paper_dir),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
