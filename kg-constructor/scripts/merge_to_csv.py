#!/usr/bin/env python3
"""
Convert per-paper KG JSONs into per-paper CSVs and concatenate them into one
merged CSV. Two modes:

    merge_to_csv.py --per-paper <per_paper_json_dir> <metadata_path> <out_csv_dir>
    merge_to_csv.py --merge     <per_paper_csv_dir>  <out_csv>

Schema matches the project's 26-column EXPECTED_COLUMNS from validate_kg.py
exactly. Citation flattening mirrors extract_kg_csv.py:234-249.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


EXPECTED_COLUMNS = [
    "custom_id", "journal", "year", "month", "title", "section", "filename",
    "source", "source_identifier", "source_type", "source_category",
    "source_extracted_definition", "source_generated_definition",
    "relationship", "relationship_category",
    "target", "target_identifier", "target_type", "target_category",
    "target_extracted_definition", "target_generated_definition",
    "species", "basis",
    "extracted_associated_process_or_pathway", "generated_associated_process_or_pathway",
    "relevant_citations",
]


def flatten_citations(citations) -> str:
    """Match extract_kg_csv.py:234-249 exactly."""
    if not isinstance(citations, list) or not citations:
        return ""
    if all(isinstance(c, dict) for c in citations):
        parts = []
        for c in citations:
            ct = c.get('citation_text', 'NA')
            rk = c.get('reference_key', 'NA')
            if ct == "ref" and rk and rk.startswith("reference_key_"):
                ct = rk.replace("reference_key_", "")
            parts.append(f"{ct} | {rk}")
        return "; ".join(parts)
    if all(isinstance(c, str) for c in citations):
        return "; ".join(citations)
    return "; ".join(str(c) for c in citations)


def build_custom_id_lookup(metadata: dict) -> dict:
    """Build (filename, section) -> custom_id mapping from metadata.json."""
    requests = metadata.get("requests", {})
    return {
        (r.get("filename", ""), r.get("section", "")): cid
        for cid, r in requests.items()
    }


def rows_from_paper_json(paper_json: dict, custom_id_by_fs: dict) -> list:
    filename = paper_json.get("filename", "")
    title = paper_json.get("title", "")
    journal = paper_json.get("journal", "")
    year = paper_json.get("year", "")
    month = paper_json.get("month", "")

    rows = []
    for section, triples in paper_json.get("sections", {}).items():
        custom_id = custom_id_by_fs.get((filename, section), "")
        for rel in triples:
            if not isinstance(rel, dict):
                continue
            row = {
                "custom_id": custom_id,
                "journal": journal,
                "year": year,
                "month": month,
                "title": title,
                "section": section,
                "filename": filename,
                "source": rel.get("source", ""),
                "source_identifier": rel.get("source_identifier", ""),
                "source_type": rel.get("source_type", ""),
                "source_category": rel.get("source_category", ""),
                "source_extracted_definition": rel.get("source_extracted_definition", ""),
                "source_generated_definition": rel.get("source_generated_definition", ""),
                "relationship": rel.get("relationship", ""),
                "relationship_category": rel.get("relationship_category", ""),
                "target": rel.get("target", ""),
                "target_identifier": rel.get("target_identifier", ""),
                "target_type": rel.get("target_type", ""),
                "target_category": rel.get("target_category", ""),
                "target_extracted_definition": rel.get("target_extracted_definition", ""),
                "target_generated_definition": rel.get("target_generated_definition", ""),
                "species": rel.get("species", ""),
                "basis": rel.get("basis", ""),
                "extracted_associated_process_or_pathway": rel.get(
                    "extracted_associated_process_or_pathway", "",
                ),
                "generated_associated_process_or_pathway": rel.get(
                    "generated_associated_process_or_pathway", "",
                ),
                "relevant_citations": flatten_citations(rel.get("relevant_citations", [])),
            }
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPECTED_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def cmd_per_paper(args):
    per_paper_dir = Path(args.per_paper_dir).resolve()
    metadata_path = Path(args.metadata_path).resolve()
    out_dir = Path(args.out_csv_dir).resolve()

    if not per_paper_dir.is_dir():
        print(f"ERROR: missing {per_paper_dir}", file=sys.stderr)
        sys.exit(2)
    if not metadata_path.is_file():
        print(f"ERROR: missing {metadata_path}", file=sys.stderr)
        sys.exit(2)

    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    custom_id_by_fs = build_custom_id_lookup(metadata)

    papers_written = 0
    total_rows = 0
    paper_files = sorted(per_paper_dir.glob("*.json"))
    for pf in paper_files:
        try:
            paper_json = json.loads(pf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"WARN: {pf.name}: {e}", file=sys.stderr)
            continue
        rows = rows_from_paper_json(paper_json, custom_id_by_fs)
        out_path = out_dir / f"{pf.stem}.csv"
        write_csv(out_path, rows)
        papers_written += 1
        total_rows += len(rows)

    summary = {
        "mode": "per-paper",
        "papers_written": papers_written,
        "total_rows": total_rows,
        "out_dir": str(out_dir),
    }
    print(json.dumps(summary, indent=2))


def cmd_merge(args):
    csv_dir = Path(args.csv_dir).resolve()
    out_csv = Path(args.out_csv).resolve()

    if not csv_dir.is_dir():
        print(f"ERROR: missing {csv_dir}", file=sys.stderr)
        sys.exit(2)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    paper_csvs = sorted(csv_dir.glob("*.csv"))
    if not paper_csvs:
        print(f"ERROR: no CSVs in {csv_dir}", file=sys.stderr)
        sys.exit(3)

    total_rows = 0
    papers_merged = 0
    with out_csv.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=EXPECTED_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for pcsv in paper_csvs:
            with pcsv.open("r", encoding="utf-8", newline="") as fin:
                reader = csv.DictReader(fin)
                if reader.fieldnames != EXPECTED_COLUMNS:
                    print(
                        f"ERROR: column mismatch in {pcsv.name}\n"
                        f"  expected: {EXPECTED_COLUMNS}\n"
                        f"  found:    {reader.fieldnames}",
                        file=sys.stderr,
                    )
                    sys.exit(4)
                for row in reader:
                    writer.writerow(row)
                    total_rows += 1
            papers_merged += 1

    summary = {
        "mode": "merge",
        "papers_merged": papers_merged,
        "total_rows": total_rows,
        "out_csv": str(out_csv),
    }
    print(json.dumps(summary, indent=2))


USAGE = """\
usage:
  merge_to_csv.py --per-paper <per_paper_json_dir> <metadata_path> <out_csv_dir>
  merge_to_csv.py --merge     <per_paper_csv_dir>  <out_csv>
"""


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)

    mode = argv[0]
    rest = argv[1:]

    if mode == "--per-paper":
        if len(rest) != 3:
            print("ERROR: --per-paper requires <per_paper_json_dir> <metadata_path> <out_csv_dir>",
                  file=sys.stderr)
            print(USAGE, file=sys.stderr)
            sys.exit(2)
        ns = argparse.Namespace(
            per_paper_dir=rest[0],
            metadata_path=rest[1],
            out_csv_dir=rest[2],
        )
        cmd_per_paper(ns)
        return

    if mode == "--merge":
        if len(rest) != 2:
            print("ERROR: --merge requires <per_paper_csv_dir> <out_csv>", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            sys.exit(2)
        ns = argparse.Namespace(
            csv_dir=rest[0],
            out_csv=rest[1],
        )
        cmd_merge(ns)
        return

    print(f"ERROR: unknown mode {mode!r}. Use --per-paper or --merge.", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
