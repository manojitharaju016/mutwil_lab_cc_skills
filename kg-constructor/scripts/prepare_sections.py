#!/usr/bin/env python3
"""
Walk a directory of plant-paper JSONs, split each into sections using the
bundled `extract_sections` port, and write per-section .txt files plus a
metadata.json that maps each custom_id to {journal, year, month, title,
filename, section}.

Inputs:
    <input_dir>      directory to walk recursively for paper JSONs
    <output_dir>     where to write `sections/` and `metadata.json`

The script handles publisher dir variants automatically: OUP year/issue trees,
Elsevier numeric month subdirs (01..12), Springer `json/` subfolders, Nature
`json_articles/PMC/`, Wiley flat layouts. It does not require a flag for it.

Files skipped during discovery:
    - manifest/index JSONs: *_ids.json, *_metadata.json, batch_ids.json
    - any *.jsonl
    - files smaller than ~500 bytes
    - papers whose top-level JSON has none of sections[], full_text[],
      structure[], or content
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_sections import (
    extract_sections, extract_abbreviations, MONTH_NAMES, MONTH_ORDER,
)


MANIFEST_GLOBS = ('_ids.json', '_metadata.json', 'batch_ids.json')
MIN_PAPER_BYTES = 500
MAX_CUSTOM_ID_LEN = 64
MAX_SUFFIX_LEN = 20


def is_paper_json_path(p: Path) -> bool:
    name = p.name.lower()
    if name.endswith('.jsonl'):
        return False
    if not name.endswith('.json'):
        return False
    if name in {'batch_ids.json', 'metadata.json'}:
        return False
    for suffix in MANIFEST_GLOBS:
        if name.endswith(suffix):
            return False
    try:
        if p.stat().st_size < MIN_PAPER_BYTES:
            return False
    except OSError:
        return False
    return True


def load_paper_json(p: Path):
    """Read a paper JSON, trying multiple encodings before giving up."""
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with p.open("r", encoding=enc) as f:
                return json.load(f)
        except UnicodeDecodeError:
            continue
        except (OSError, json.JSONDecodeError) as e:
            return e
    return UnicodeDecodeError("all", b"", 0, 1, "no encoding worked")


def paper_has_content_keys(data) -> bool:
    if not isinstance(data, dict):
        return isinstance(data, list) and len(data) > 0
    for key in ("sections", "full_text", "structure", "content", "abstract"):
        v = data.get(key)
        if v:
            return True
    return False


def normalize_month(value):
    """Accept 'May', 'may', '5', 5, '05' and return both the long name and
    numeric ordinal. Returns (name, ord) where either may be ''."""
    if value is None or value == "":
        return "", ""
    if isinstance(value, int):
        return MONTH_NAMES.get(value, ""), value
    s = str(value).strip()
    if not s:
        return "", ""
    if s.isdigit():
        n = int(s)
        return MONTH_NAMES.get(n, ""), n
    n = MONTH_ORDER.get(s.lower())
    if n:
        return MONTH_NAMES[n], n
    return s, ""


def derive_paper_metadata(data, file_path: Path, input_root: Path) -> dict:
    """Pull journal/year/month/title from the paper JSON and filesystem path."""
    journal = ""
    year = ""
    month_name = ""
    month_ord = ""
    title = ""

    if isinstance(data, dict):
        journal = (data.get("journal") or "").strip() or journal
        title = (data.get("title") or "").strip() or title
        y = data.get("year")
        if y is not None and str(y).strip():
            year = str(y).strip()
        m = data.get("month") if data.get("month") is not None else data.get("month_ord")
        month_name, month_ord = normalize_month(m)

    try:
        rel = file_path.relative_to(input_root)
        parts = rel.parts[:-1]
    except ValueError:
        parts = ()

    if not journal:
        for seg in parts:
            seg_l = seg.lower()
            if seg_l in ("json", "json_articles", "pmc"):
                continue
            if seg_l.isdigit():
                continue
            journal = seg
            break

    if not year:
        for seg in parts:
            if seg.isdigit() and 1900 <= int(seg) <= 2100:
                year = seg
                break

    if not month_name:
        for seg in parts:
            if seg.isdigit() and 1 <= len(seg) <= 2:
                try:
                    n = int(seg)
                    if 1 <= n <= 12:
                        month_name, month_ord = normalize_month(n)
                        break
                except ValueError:
                    pass

    return {
        "journal": journal,
        "year": year,
        "month": month_name,
        "month_ord": month_ord,
        "title": title,
        "filename": file_path.name,
    }


def make_custom_id(filename: str, section: str, year, month_ord) -> str:
    """Replicate anthropic_batch.py custom_id format with the 64-char limit."""
    clean_fname = filename.replace(".json", "")
    sanitized_fname = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_fname)
    suffix = f"_{section}"
    sanitized_suffix = re.sub(r'[^a-zA-Z0-9_-]', '_', suffix)
    combo_hash = hashlib.md5(
        f"{clean_fname}:{year}:{month_ord}:{section}".encode()
    ).hexdigest()[:6]
    hash_part = f"_{combo_hash}"
    if len(sanitized_suffix) > MAX_SUFFIX_LEN:
        sanitized_suffix = sanitized_suffix[:MAX_SUFFIX_LEN]
    max_fname_len = MAX_CUSTOM_ID_LEN - len(sanitized_suffix) - len(hash_part)
    if len(sanitized_fname) > max_fname_len:
        sanitized_fname = sanitized_fname[:max_fname_len]
    cid = f"{sanitized_fname}{hash_part}{sanitized_suffix}"
    assert len(cid) <= MAX_CUSTOM_ID_LEN, (cid, len(cid))
    return cid


def assemble_section_text(sections: dict, sec_name: str, title: str,
                          abbreviations_text: str) -> str:
    text = sections.get(sec_name, "")
    if not text:
        return ""
    if sec_name == 'abstract' and title:
        final_text = f"Title: {title}\n\n{text}"
    elif sec_name.startswith('custom_') or sec_name.startswith('results_and_discussion_'):
        header_text = sections.get(f"_header_{sec_name}", "")
        if header_text:
            final_text = f"Section: {header_text}\n\n{text}"
        else:
            final_text = text
    else:
        final_text = text

    dive = sections.get('dive', "")
    if dive:
        final_text += f"\n\nDive Curated Terms:\n{dive}"
    if abbreviations_text:
        final_text += f"\n\nAbbreviations:\n{abbreviations_text}"
    return final_text


STANDARD_SECS = ['abstract', 'introduction', 'results', 'discussion', 'results_and_discussion']


def derive_paper_id(filename: str) -> str:
    """Stable id used to group sections under a single paper."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', filename.replace('.json', ''))


def discover_paper_jsons(input_dir: Path):
    paper_paths = []
    skipped = {"manifest": 0, "tiny": 0, "non_json": 0}
    for root, dirs, files in os.walk(input_dir, followlinks=False):
        for fname in files:
            fpath = Path(root) / fname
            lower = fname.lower()
            if not lower.endswith('.json'):
                skipped["non_json"] += 1
                continue
            if is_paper_json_path(fpath):
                paper_paths.append(fpath)
            else:
                if fpath.stat().st_size < MIN_PAPER_BYTES if fpath.exists() else True:
                    skipped["tiny"] += 1
                else:
                    skipped["manifest"] += 1
    paper_paths.sort()
    return paper_paths, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir")
    ap.add_argument("output_dir")
    ap.add_argument("--journal", default=None,
                    help="Optional: filter to this journal slug (matched against metadata or path).")
    ap.add_argument("--force-redo", action="store_true",
                    help="Overwrite existing section .txt files instead of skipping.")
    args = ap.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not input_dir.is_dir():
        print(f"ERROR: input dir does not exist: {input_dir}", file=sys.stderr)
        sys.exit(2)

    sections_dir = output_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    paper_paths, skipped = discover_paper_jsons(input_dir)
    if not paper_paths:
        print(f"ERROR: no paper JSONs found under {input_dir}", file=sys.stderr)
        print(f"  skipped: {skipped}", file=sys.stderr)
        sys.exit(3)

    metadata = {"requests": {}}
    seen_custom_ids = set()
    papers_processed = 0
    sections_written = 0
    papers_no_content = 0
    papers_load_failed = 0
    paper_id_to_filename = {}

    for fpath in paper_paths:
        loaded = load_paper_json(fpath)
        if isinstance(loaded, Exception):
            papers_load_failed += 1
            print(f"WARN: failed to load {fpath.name}: {loaded}", file=sys.stderr)
            continue
        data = loaded

        if not paper_has_content_keys(data):
            papers_no_content += 1
            continue

        meta = derive_paper_metadata(data, fpath, input_dir)
        if args.journal and meta["journal"] != args.journal:
            continue

        try:
            sections = extract_sections(data)
        except Exception as e:
            papers_load_failed += 1
            print(f"WARN: extract_sections failed on {fpath.name}: {e}", file=sys.stderr)
            continue

        abbreviations_text = extract_abbreviations(data)

        custom_secs = [
            k for k in sections
            if (k.startswith('custom_') or k.startswith('results_and_discussion_'))
            and not k.startswith('_header_')
        ]
        all_sec_names = STANDARD_SECS + custom_secs

        any_section_written = False
        paper_id = derive_paper_id(fpath.name)
        paper_id_to_filename[paper_id] = fpath.name

        for sec_name in all_sec_names:
            section_text = assemble_section_text(
                sections, sec_name, meta["title"], abbreviations_text,
            )
            if not section_text.strip():
                continue

            custom_id = make_custom_id(
                fpath.name, sec_name, meta["year"], meta["month_ord"],
            )
            if custom_id in seen_custom_ids:
                base = custom_id
                n = 2
                while custom_id in seen_custom_ids:
                    tail = f"_dup{n}"
                    custom_id = base[: MAX_CUSTOM_ID_LEN - len(tail)] + tail
                    n += 1
            seen_custom_ids.add(custom_id)

            out_path = sections_dir / f"{custom_id}.txt"
            if out_path.exists() and not args.force_redo:
                pass
            else:
                out_path.write_text(section_text, encoding="utf-8")

            metadata["requests"][custom_id] = {
                "journal": meta["journal"],
                "year": meta["year"],
                "month": meta["month"],
                "title": meta["title"],
                "filename": meta["filename"],
                "section": sec_name,
                "paper_id": paper_id,
            }
            sections_written += 1
            any_section_written = True

        if any_section_written:
            papers_processed += 1
        else:
            papers_no_content += 1

    metadata["_paper_id_to_filename"] = paper_id_to_filename
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "papers_found": len(paper_paths),
        "papers_processed": papers_processed,
        "papers_no_content": papers_no_content,
        "papers_load_failed": papers_load_failed,
        "sections_written": sections_written,
        "skipped_files": skipped,
        "metadata_path": str(metadata_path),
        "sections_dir": str(sections_dir),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
